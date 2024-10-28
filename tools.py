import asyncio
import base64
import httpx
import json
import re
import redis
import time
import vertexai
from decouple import config
from fastapi import HTTPException
from vertexai.generative_models import GenerativeModel
from schemas import ReviewResponseModel, FileTreeModel
from typing import Optional, Dict, Union
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("app.log")],
)
logger = logging.getLogger(__name__)

github_token = config("GITHUB_TOKEN")
project_id = (config("PROJECT_ID"),)


class CodeReviewService:
    RATE_LIMIT_STATUS_CODE = 403
    RETRY_STATUS_CODES = {429, 500}
    MAX_RETRIES = 5
    BACKOFF_FACTOR = 2
    SAFETY_RETRY_LIMIT = 3
    SAFETY_BACKOFF_FACTOR = 2

    redis_client = redis.StrictRedis(
        host=config("REDIS_HOST"),
        port=int(config("REDIS_PORT")),
        decode_responses=True,
    )

    def __init__(
        self,
        model_name: str = "gemini-1.5-flash-001",
    ):
        self.github_token = github_token
        self.model = GenerativeModel(model_name=model_name)
        vertexai.init(project=project_id, location="us-central1")

    def _get_github_headers(self) -> Dict[str, str]:
        if not self.github_token:
            raise HTTPException(status_code=500, detail="GitHub token is not set.")
        return {"Authorization": f"token {self.github_token}"}

    async def _get_file_content(self, file_url: str) -> Optional[str]:
        attempt = 0
        while attempt < self.MAX_RETRIES:
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        file_url, headers=self._get_github_headers()
                    )
                response.raise_for_status()

                file_data = response.json()
                return (
                    base64.b64decode(file_data["content"]).decode("utf-8")
                    if "content" in file_data
                    else None
                )

            except httpx.HTTPStatusError as e:
                if response.status_code == self.RATE_LIMIT_STATUS_CODE:
                    logger.warning(
                        f"Rate limit encountered (403) for {file_url}. "
                        f"Waiting {self.BACKOFF_FACTOR} seconds before retrying."
                    )
                    await asyncio.sleep(self.BACKOFF_FACTOR)
                    attempt += 1
                elif response.status_code in self.RETRY_STATUS_CODES:
                    attempt += 1
                    backoff_time = self.BACKOFF_FACTOR**attempt
                    logger.warning(
                        f"Retrying fetch for file content from {file_url} in {backoff_time} seconds "
                        f"due to status {response.status_code} (Attempt {attempt}/{self.MAX_RETRIES})"
                    )
                    await asyncio.sleep(backoff_time)
                else:
                    logger.error(f"Failed to fetch file content from {file_url}: {e}")
                    raise HTTPException(
                        status_code=response.status_code,
                        detail="Failed to fetch file content.",
                    )
            except Exception as e:
                logger.error(
                    f"Unexpected error fetching file content from {file_url}: {e}"
                )
                raise HTTPException(
                    status_code=500, detail="Unexpected error fetching file content."
                )

        raise HTTPException(
            status_code=500, detail="Exceeded max retries for fetching file content."
        )

    async def fetch_all_files_content(
        self, owner: str, repo: str, path: str = ""
    ) -> Dict[str, Optional[str]]:
        files_content = {}
        page = 1

        while True:
            url = (
                f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
                f"?page={page}&per_page=100"
            )

            attempt = 0
            while attempt < self.MAX_RETRIES:
                try:
                    async with httpx.AsyncClient() as client:
                        response = await client.get(
                            url, headers=self._get_github_headers()
                        )
                        response.raise_for_status()

                        repo_content = response.json()
                        if not repo_content:
                            return files_content

                        tasks = [
                            self._fetch_content_recursive(
                                item, owner, repo, files_content
                            )
                            for item in repo_content
                        ]
                        await asyncio.gather(*tasks)
                        break

                except httpx.HTTPStatusError as e:
                    if response.status_code == self.RATE_LIMIT_STATUS_CODE:
                        reset_time = int(response.headers.get("X-RateLimit-Reset", 0))
                        sleep_time = max(0, reset_time - int(time.time()))
                        logger.warning(
                            f"Rate limit reached. Sleeping for {sleep_time} seconds."
                        )
                        await asyncio.sleep(sleep_time)
                    elif response.status_code in self.RETRY_STATUS_CODES:
                        attempt += 1
                        backoff_time = self.BACKOFF_FACTOR**attempt
                        logger.warning(
                            f"Retrying fetch for repository content due to status {response.status_code} "
                            f"(Attempt {attempt}/{self.MAX_RETRIES}). Backing off for {backoff_time} seconds."
                        )
                        await asyncio.sleep(backoff_time)
                    else:
                        logger.error(
                            f"Failed to fetch repository content from {url}: {e}"
                        )
                        raise HTTPException(
                            status_code=response.status_code,
                            detail="Failed to fetch repository content.",
                        )
                except Exception as e:
                    logger.error(
                        f"Unexpected error fetching repository content from {url}: {e}"
                    )
                    raise HTTPException(
                        status_code=500,
                        detail="Unexpected error fetching repository content.",
                    )

            page += 1
            if len(repo_content) < 100:
                break

        return files_content

    async def _fetch_content_recursive(
        self, item: dict, owner: str, repo: str, files_content: Dict[str, Optional[str]]
    ) -> None:
        if item["type"] == "file":
            file_content = await self._get_file_content(item["url"])
            files_content[item["path"]] = file_content
        elif item["type"] == "dir":
            subdir_content = await self.fetch_all_files_content(
                owner, repo, item["path"]
            )
            files_content.update(subdir_content)

    @staticmethod
    def build_file_structure(files: list) -> Dict[str, Union[None, dict]]:
        file_tree = {}
        for file_path in files:
            parts = file_path.split("/")
            current_level = file_tree
            for part in parts:
                if part not in current_level:
                    current_level[part] = {} if part != parts[-1] else None
                current_level = (
                    current_level[part]
                    if current_level[part] is not None
                    else current_level
                )
        return file_tree

    @classmethod
    def cache_result(cls, key: str, value: dict, ttl: int = 3600) -> None:
        cls.redis_client.set(key, json.dumps(value), ex=ttl)

    @classmethod
    def get_cached_result(cls, key: str) -> Optional[dict]:
        cached_data = cls.redis_client.get(key)
        return json.loads(cached_data) if cached_data else None

    @staticmethod
    def parse_review_response(
        response_text: str, found_files: FileTreeModel
    ) -> ReviewResponseModel:
        downsides_comments = re.search(
            r"### Downsides:\n(.*?)(?=\n###|$)", response_text, re.DOTALL
        )
        rating = re.search(r"### Rating:\n(.*?)(?=\n###|$)", response_text, re.DOTALL)
        conclusion = re.search(
            r"### Conclusion:\n(.*?)(?=\n###|$)", response_text, re.DOTALL
        )

        return ReviewResponseModel(
            found_files=FileTreeModel.parse_obj(found_files),
            downsides_comments=(
                downsides_comments.group(1).strip() if downsides_comments else ""
            ),
            rating=rating.group(1).strip() if rating else "",
            conclusion=conclusion.group(1).strip() if conclusion else "",
        )

    async def generate_review(
        self, files_content: Dict[str, Optional[str]], candidate_level: str
    ) -> ReviewResponseModel:
        file_structure = self.build_file_structure(list(files_content.keys()))
        code_snippets = "\n".join(
            [
                f"File: {filename}\n{content}"
                for filename, content in files_content.items()
            ]
        )

        prompt = (
            f"Review this code for a {candidate_level} level assignment.\n\n"
            f"Files found in the repository:\n{file_structure}\n\n"
            f"Code snippets:\n{code_snippets}\n\n"
            "Provide feedback exactly in the following format, ensuring each section starts with the specified label:\n"
            "### Start of Review\n"
            "### Downsides:\n- List any issues or missing features in the code.\n\n"
            "### Rating:\n- Provide a rating out of 5 and briefly justify the score.\n\n"
            "### Conclusion:\n- Summarize the main points and give recommendations for improvements.\n"
            "### End of Review"
        )

        safety_attempt = 0
        while safety_attempt < self.SAFETY_RETRY_LIMIT:
            try:
                response = self.model.generate_content(prompt)
                if (
                    not response
                    or not hasattr(response, "text")
                    or response.candidates[0].finish_reason == "SAFETY"
                ):
                    logger.warning(
                        f"Safety filter triggered on attempt {safety_attempt + 1}. "
                        f"Retrying after backoff..."
                    )
                    safety_attempt += 1
                    backoff_time = self.SAFETY_BACKOFF_FACTOR**safety_attempt
                    await asyncio.sleep(backoff_time)
                    continue

                response_text = response.text
                return self.parse_review_response(
                    response_text, FileTreeModel.parse_obj(file_structure)
                )

            except Exception as e:
                logger.error(f"An error occurred while generating the review: {e}")
                raise HTTPException(
                    status_code=500,
                    detail="An error occurred while generating the review.",
                )

        raise HTTPException(
            status_code=400,
            detail="Review generation blocked by safety filters after multiple attempts.",
        )
