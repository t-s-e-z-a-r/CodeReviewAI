from pydantic import BaseModel, HttpUrl, RootModel
from typing import Dict, Optional, Any
from enum import Enum


class FileTreeModel(RootModel[Optional[Dict[str, Any]]]):
    pass


class ReviewResponseModel(BaseModel):
    found_files: FileTreeModel
    downsides_comments: str
    rating: str
    conclusion: str


class CandidateLevel(str, Enum):
    junior = "Junior"
    middle = "Middle"
    senior = "Senior"


class ReviewRequest(BaseModel):
    assignment_description: str = "GraphQL simple API"
    github_repo_url: HttpUrl = "https://github.com/t-s-e-z-a-r/GraphQL"
    candidate_level: CandidateLevel

    def to_dict(self):
        data = self.dict()
        data["github_repo_url"] = str(self.github_repo_url)
        return data
