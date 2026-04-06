param(
  [switch]$WithReplies,
  [string]$Suite = "backend/evals/retrieval_baseline.json",
  [string]$WriteReport = ""
)

$scriptArgs = @("scripts/eval/run_retrieval_eval.py", "--suite", $Suite)

if ($WithReplies) {
  $scriptArgs += "--with-replies"
}

if ($WriteReport) {
  $scriptArgs += @("--write-report", $WriteReport)
}

py -3 @scriptArgs
