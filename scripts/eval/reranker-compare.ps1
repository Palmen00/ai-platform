param(
    [string]$Suite = "backend/evals/synthetic_signal_cases.json",
    [string]$Model = "cross-encoder/ms-marco-MiniLM-L-6-v2",
    [int]$Limit = 6,
    [int]$CandidateLimit = 12
)

py -3 .\scripts\eval\prototype_reranker_compare.py --suite $Suite --model $Model --limit $Limit --candidate-limit $CandidateLimit
