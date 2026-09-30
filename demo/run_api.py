"""Run the SynTrends Phase B HTTP API.

    uvicorn api.main:app --reload --port 8080

Or:

    python -m demo.run_api
"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run("api.main:app", host="127.0.0.1", port=8080, reload=False)
