$ErrorActionPreference = "Stop"

$body = Get-Content ".\tests\golden\case_001_nominal.json" -Raw -Encoding UTF8

$response = Invoke-RestMethod `
    -Method Post `
    -Uri "http://127.0.0.1:8010/analyze" `
    -ContentType "application/json" `
    -Body $body

$response | ConvertTo-Json -Depth 8
