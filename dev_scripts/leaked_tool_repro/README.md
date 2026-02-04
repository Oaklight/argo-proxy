# Leaked Tool Call Reproduction Scripts

This directory contains scripts and data for reproducing and investigating the leaked tool call issue with Claude models.

## Background

When using Claude models (especially Claude 4.5 Opus) through the ARGO API, tool calls are sometimes "leaked" into the text content instead of being returned through the proper `tool_calls` field.

## Files

- `leaked_tool_call_investigation.md` - Detailed investigation report
- `leaked_tool_20260128_171422_165810.json` - Log file for case 1
- `leaked_tool_20260128_171653_513513.json` - Log file for case 2
- `repro_case_1.py` - Reproduction script for case 1
- `repro_case_2.py` - Reproduction script for case 2

## Usage

### Prerequisites

```bash
pip install httpx
```

### Running the Scripts

1. Start argo-proxy on the default port (8000):
   ```bash
   argo-proxy
   ```

2. Run a reproduction script:
   ```bash
   python repro_case_1.py
   ```

3. To also test directly against the ARGO API:
   ```bash
   TEST_DIRECT=true python repro_case_1.py
   ```

### Environment Variables

- `ARGO_PROXY_URL` - URL of the argo-proxy server (default: `http://localhost:8000`)
- `ARGO_DIRECT_URL` - URL of the direct ARGO API (default: `https://apps-dev.inside.anl.gov/argoapi/api/v1/resource/chat`)
- `TEST_DIRECT` - Set to `true` to also test direct API calls

## Expected Output

### If the bug is reproduced:
```
⚠️  LEAKED TOOL CALL DETECTED!
Pattern found: {'id': 'toolu_
```

### If the bug is NOT reproduced:
```
✓ No leaked tool calls detected in content
Tool calls returned properly:
  [0] bash
```

## Investigation Status

See `leaked_tool_call_investigation.md` for the full investigation report.