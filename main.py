import hashlib
from fastapi import FastAPI, HTTPException
from decouple import config
from typing import Union

from tools import CodeReviewService
from schemas import ReviewRequest, ReviewResponseModel

app = FastAPI()


@app.post("/review", response_model=ReviewResponseModel)
async def create_review(review: ReviewRequest) -> Union[ReviewResponseModel, dict]:
    code_review_service = CodeReviewService()
    url_parts = review.github_repo_url.path.strip("/").split("/")
    if len(url_parts) < 2:
        raise HTTPException(status_code=400, detail="Invalid GitHub repository URL.")
    owner, repo = url_parts[0], url_parts[1]
    search_string = f"{str(review.github_repo_url)} {review.candidate_level}"
    cache_key = hashlib.md5(search_string.encode()).hexdigest()

    cached_result = code_review_service.get_cached_result(cache_key)
    if cached_result:
        return cached_result

    files_content = await code_review_service.fetch_all_files_content(owner, repo)
    review_response = await code_review_service.generate_review(
        files_content, review.candidate_level
    )
    # code_review_service.cache_result(
    #     cache_key,
    #     (
    #         review_response
    #         if isinstance(review_response, dict)
    #         else review_response.dict()
    #     ),
    #     ttl=3600,
    # )

    return review_response
