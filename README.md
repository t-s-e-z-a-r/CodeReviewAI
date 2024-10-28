# Code Review Service with Vertex AI and GitHub Integration

This project is a **Code Review API** service that leverages **Vertex AI** from Google Cloud Platform (GCP) as an AI model provider. It fetches code from a specified GitHub repository and performs code analysis based on the specified candidate level. The service handles GitHub's rate limits and integrates backoff strategies to improve stability. The application uses **FastAPI** as the web framework, along with **Redis** for caching and **Docker** for easy deployment.

## Features

- **AI-powered code review**: Utilizes Vertex AI (GCP's alternative to OpenAI's ChatGPT) for code analysis and review.
- **GitHub Integration**: Fetches code files from public GitHub repositories.
- **Error handling and retries**: Implements exponential backoff and retry logic for rate-limited or intermittent API responses.
- **Caching**: Uses Redis to cache responses and reduce repeated API calls.
- **Dockerized**: Easily deployable with Docker and Docker Compose.

## Prerequisites

To run this project, you need:
- **Docker** and **Docker Compose** installed.
- A **GCP Project** with Vertex AI enabled.
- **GitHub Access Token** (for accessing private repositories if needed).
- **Redis** (set up via Docker Compose in this project).

## Configuration

1. Clone this repository:
   ```bash
   git clone https://github.com/t-s-e-z-a-r/CodeReviewAI
   cd CodeReviewAI
   ```

2. Set up your environment variables in a `.env` file:
   ```
   GITHUB_TOKEN=your_github_token
   GOOGLE_APPLICATION_CREDENTIALS=app/your_credentials.json from GCP
   PROJECT_ID=your_gcp_project_id
   REDIS_HOST=redis
   REDIS_PORT=6379
   ```

   - **GITHUB_TOKEN**: GitHub access token for accessing repositories.
   - **PROJECT_ID**: GCP Project ID where Vertex AI is enabled.
   - **REDIS_HOST** and **REDIS_PORT**: Redis configuration (Docker Compose automatically handles these).

## Getting Started

To run this project using Docker Compose:

1. **Build and start** the containers:
   ```bash
   docker-compose up --build
   ```

2. Once the services start, the FastAPI server will be available at `http://localhost:8000`.

3. You can test the API by sending requests to `http://localhost:8000/review`. For instance:

   ```bash
   curl -X POST "http://localhost:8000/review" -H "Content-Type: application/json" -d '{
       "github_repo_url": "https://github.com/testuser/testrepo",
       "candidate_level": "Junior",
       "assignment_description": "Test task"
   }'
   ```

## API Endpoints

- **POST /review** - Submits a request for a code review on the specified GitHub repository. Requires JSON payload:
  
  ```json
  {
      "github_repo_url": "https://github.com/user/repo",
      "candidate_level": "Junior",
      "assignment_description": "Describe the assignment here"
  }
  ```

## Project Structure

- **main.py**: Entry point of the FastAPI application.
- **tools.py**: Contains the main `CodeReviewService` class, which handles API interactions, error handling, retries, and backoff strategies.
- **schemas.py**: Defines data models used in request validation and response formatting.
- **Dockerfile**: Specifies the Docker image build instructions for the FastAPI app.
- **docker-compose.yml**: Configures services, including Redis, for a complete environment.
- **tests/**: Contains test cases for the API using `pytest` and `httpx`.

## Handling Vertex AI Safety and Rate Limits

The project uses **Vertex AI**'s safety filters to prevent unsafe content generation and retries requests if safety filters or rate limits are triggered. Each retry includes a backoff strategy to avoid hitting rate limits frequently.

## Dependencies

- **FastAPI**: Web framework for building APIs with Python.
- **Redis**: Caching layer to store intermediate responses.
- **httpx**: Async HTTP client used to interact with GitHub's API.
- **vertexai**: Library to integrate with GCP's Vertex AI.

## Running Tests

To run tests, execute this in backend container:
```bash
pytest tests --asyncio-mode=auto
```

The tests cover error handling, caching, and the main review functionality of the application.

---

# Second Part
## 1. Infrastructure and Load Balancing
- **Horizontal Scaling**: Deploy multiple instances of the application on a Kubernetes cluster to distribute the load across various nodes. This setup enables horizontal scaling to meet spikes in review requests.
- **Load Balancing**: Use a load balancer (like GCP’s Load Balancer or an Nginx-based solution) to evenly distribute incoming requests to the available instances. This setup minimizes request bottlenecks, ensuring the system remains responsive under heavy load.
- **Autoscaling**: Implement autoscaling policies to dynamically add or remove instances based on traffic patterns. This approach maintains optimal resource usage, avoiding under- or over-provisioning.
## 2. Database and Caching
- **Database Sharding and Replication**: Split data across multiple database nodes by sharding, which enhances read/write performance for large datasets. Database replication also provides fault tolerance and improves read performance.
- **Redis Cache for Frequent Data**: Use Redis to cache frequently accessed data such as user review histories, common repository files, or frequently requested data to reduce repeated database calls. This will reduce database load and improve response times.
- **Asynchronous Task Queue**: Offload heavy or time-consuming tasks (e.g., fetching large repositories or file processing) to a background task queue (such as Celery with Redis or Google Cloud Tasks). The main API can quickly respond to users, while tasks are processed in the background.
## 3. API Rate Limits and Cost Management for Vertex AI and GitHub APIs
- **Rate-Limiting with Exponential Backoff**: Implement retry logic with exponential backoff for both GitHub and Vertex AI API calls. This approach helps to manage rate limits effectively and ensures compliance with the API usage policies.
- **Pooling API Calls**: Aggregate multiple small requests into single large requests where possible. For instance, batch file fetching from GitHub instead of multiple individual calls. This reduces the number of API calls and maximizes API efficiency.
- **Cost Optimization**: Monitor the Vertex AI usage closely. Implement tiered caching for different levels of requests (e.g., a persistent cache for repetitive AI requests) to minimize unnecessary requests and thus reduce costs. For low-priority requests, consider using lower-cost alternative models.
## 4. Handling Large Repositories with Pagination
- **GitHub API Pagination**: Implement pagination support for repositories with over 100 files. When fetching repository files, handle paginated responses to systematically retrieve files without hitting GitHub’s API limits.
- **Parallel Processing for Large File Repositories**: For repositories with many files, split file-processing tasks into parallel processes or threads, leveraging async calls to handle multiple files concurrently. This setup accelerates response times and avoids bottlenecks from large repositories.
## 5. Monitoring and Alerts
- **Monitoring Tools**: Use GCP’s built-in monitoring tools (or integrate tools like Prometheus and Grafana) to track API usage, request rates, latencies, and error rates.
- **Real-time Alerts**: Configure alerts for thresholds on API rate limits, resource usage, and error spikes to proactively address potential scaling issues before they impact users.