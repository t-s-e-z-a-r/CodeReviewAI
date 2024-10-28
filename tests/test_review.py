import pytest
from httpx import AsyncClient
from unittest.mock import patch, MagicMock
from fastapi import HTTPException
import hashlib
from main import app
from schemas import ReviewRequest


@pytest.fixture
async def client():
    async with AsyncClient(app=app, base_url="http://testserver") as client:
        yield client


@pytest.mark.asyncio
async def test_create_review_success(client):
    review_data = ReviewRequest(
        github_repo_url="https://github.com/testuser/testrepo",
        candidate_level="Junior",
        assignment_description="Test task",
    )

    with patch("tools.CodeReviewService.redis_client") as mock_redis, patch(
        "tools.CodeReviewService.fetch_all_files_content"
    ) as mock_fetch_files, patch(
        "tools.CodeReviewService.generate_review"
    ) as mock_generate_review, patch(
        "tools.GenerativeModel", MagicMock()
    ):

        mock_redis.get.return_value = None
        mock_redis.set.return_value = None

        mock_fetch_files.return_value = {"file1.py": "print('Hello World')"}
        mock_generate_review.return_value = {
            "found_files": {"file1.py": None},
            "downsides_comments": "No issues",
            "rating": "5/5",
            "conclusion": "Great job!",
        }

        response = await client.post("/review", json=review_data.to_dict())

        assert response.status_code == 200
        data = response.json()
        assert "found_files" in data
        assert data["found_files"] == {"file1.py": None}
        assert data["rating"] == "5/5"
        assert data["conclusion"] == "Great job!"


@pytest.mark.asyncio
async def test_create_review_github_error(client):
    review_data = ReviewRequest(
        github_repo_url="https://github.com/testuser/nonexistentrepo",
        candidate_level="Junior",
        assignment_description="Test task",
    )

    with patch(
        "tools.CodeReviewService.fetch_all_files_content"
    ) as mock_fetch_files, patch("tools.CodeReviewService.redis_client") as mock_redis:
        mock_fetch_files.side_effect = HTTPException(
            status_code=404, detail="Repository not found."
        )
        mock_redis.get.return_value = None
        response = await client.post("/review", json=review_data.to_dict())

        assert response.status_code == 404
        assert response.json() == {"detail": "Repository not found."}


@pytest.mark.asyncio
async def test_create_review_with_cache(client):
    review_data = ReviewRequest(
        github_repo_url="https://github.com/testuser/cachedrepo",
        candidate_level="Junior",
        assignment_description="Test task",
    )

    cached_response = {
        "found_files": {"file1.py": None},
        "downsides_comments": "Some minor issues",
        "rating": "4/5",
        "conclusion": "Good work, needs minor improvements",
    }

    with patch("tools.CodeReviewService.get_cached_result") as mock_cache, patch(
        "tools.CodeReviewService.cache_result"
    ) as mock_set_cache:

        mock_cache.return_value = cached_response

        response = await client.post("/review", json=review_data.to_dict())

        assert response.status_code == 200
        assert response.json() == cached_response
        mock_set_cache.assert_not_called()


@pytest.mark.asyncio
async def test_create_review_invalid_url(client):
    review_data = ReviewRequest(
        github_repo_url="https://invalid_url",
        candidate_level="Junior",
        assignment_description="Test task",
    )

    response = await client.post("/review", json=review_data.to_dict())

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid GitHub repository URL."}


@pytest.mark.asyncio
async def test_create_review_empty_repo(client):
    review_data = ReviewRequest(
        github_repo_url="https://github.com/testuser/emptyrepo",
        candidate_level="Junior",
        assignment_description="Test task",
    )

    with patch(
        "tools.CodeReviewService.fetch_all_files_content"
    ) as mock_fetch_files, patch(
        "tools.CodeReviewService.generate_review",
    ) as mock_generate_review, patch(
        "tools.CodeReviewService.redis_client"
    ) as mock_redis:
        mock_redis.get.return_value = None
        mock_fetch_files.return_value = {}
        mock_generate_review.return_value = {
            "found_files": {},
            "downsides_comments": "Repository is empty.",
            "rating": "N/A",
            "conclusion": "No files to review.",
        }

        response = await client.post("/review", json=review_data.to_dict())

        assert response.status_code == 200
        data = response.json()
        assert data["found_files"] == {}
        assert data["downsides_comments"] == "Repository is empty."
        assert data["rating"] == "N/A"
        assert data["conclusion"] == "No files to review."


@pytest.mark.asyncio
async def test_create_review_model_generation_error(client):
    review_data = ReviewRequest(
        github_repo_url="https://github.com/testuser/testrepo",
        candidate_level="Junior",
        assignment_description="Test task",
    )

    with patch(
        "tools.CodeReviewService.fetch_all_files_content"
    ) as mock_fetch_files, patch(
        "tools.CodeReviewService.generate_review"
    ) as mock_generate_review, patch(
        "tools.CodeReviewService.redis_client"
    ) as mock_redis:

        mock_redis.get.return_value = None
        mock_fetch_files.return_value = {"file1.py": None}

        mock_generate_review.side_effect = HTTPException(
            status_code=500, detail="Model generation error."
        )

        response = await client.post("/review", json=review_data.to_dict())

        assert response.status_code == 500
        assert response.json() == {"detail": "Model generation error."}
