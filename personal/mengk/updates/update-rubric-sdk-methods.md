*New SDK Feature: Upload & Download Judges*

You can now store and retrieve judge configurations (rubrics) through the SDK, making it easy to share and version your evaluation criteria.

*What's new:*

* `client.create_rubric(collection_id, rubric)` - Upload a rubric to the server and get back its ID
* `client.get_rubric(collection_id, rubric_id)` - Download a rubric configuration by ID
* `client.get_judge(collection_id, rubric_id)` - Download and instantiate a ready-to-use judge

*Why this matters:*

* *Version control* - Store rubric configs on the server instead of in local code
* *Sharing* - Team members can use the same rubric by ID
* *Reproducibility* - Pin to specific versions with `version=` parameter

*Quick example:*

```python
from docent.sdk.client import Docent
from docent.judges.types import Rubric

client = Docent(server_url="http://localhost:8903")

# Create and upload a rubric
rubric = Rubric(
    rubric_text="Evaluate whether the agent answered correctly...",
    output_schema={
        "type": "object",
        "properties": {
            "label": {"type": "string", "enum": ["pass", "fail"]},
            "explanation": {"type": "string"},
        },
        "required": ["label", "explanation"],
    },
)
rubric_id = client.create_rubric(collection_id, rubric)

# Later: download and run the judge
judge = client.get_judge(collection_id, rubric_id)
result = await judge(agent_run)
```

The test script at `personal/mengk/cc/test_rubric_upload_download_run.py` shows the full workflow including creating dummy agent runs and running the judge on them.
