from enum import Enum

WORKER_QUEUE_NAME = "docent_worker_queue"


class WorkerFunction(str, Enum):
    COMPUTE_EMBEDDINGS = "compute_embeddings"
    RUBRIC_JOB = "rubric_job"
    CENTROID_ASSIGNMENT_JOB = "centroid_assignment_job"  # Deprecated
    REFINEMENT_AGENT_JOB = "refinement_agent_job"
    CLUSTERING_JOB = "clustering_job"
