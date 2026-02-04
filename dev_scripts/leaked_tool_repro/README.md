# Leaked Tool Call Reproduction Scripts

This directory contains scripts and data for reproducing and investigating the leaked tool call issue with Claude models through the ARGO Gateway API.

## Background

When using Claude models (especially Claude 4.5 Opus) through the ARGO Gateway API, tool calls are sometimes "leaked" into the text content instead of being returned through the proper `tool_calls` field. **This is an upstream issue in the ARGO Gateway API, not in argo-proxy.**

## Files

### Documentation
- `leaked_tool_call_investigation.md` - Detailed investigation report

### Batch 1 Logs (2026-01-28)
- `leaked_tool_20260128_171422_165810.json` - Log file for case 1
- `leaked_tool_20260128_171653_513513.json` - Log file for case 2

### Batch 2 Logs (2026-01-31)
- `leaked_tool_20260131_114729_223329.json` - Log file for case 3 (3 read tool calls)
- `leaked_tool_20260131_114941_897350.json` - Log file for case 4 (pure tool call, no text)
- `leaked_tool_20260131_115028_795330.json` - Log file for case 5 (4 mixed tool types)

### Reproduction Scripts
- `repro_case_1.py` - Reproduction script for case 1
- `repro_case_2.py` - Reproduction script for case 2
- `repro_case_3.py` - Reproduction script for case 3 (multiple read calls)
- `repro_case_4.py` - Reproduction script for case 4 (pure tool call leak)
- `repro_case_5.py` - Reproduction script for case 5 (mixed tool types)

## Usage

### Prerequisites

```bash
pip install httpx
```

### Running the Scripts

The scripts test directly against the ARGO Gateway API to reproduce the upstream issue:

```bash
python repro_case_1.py
```

### Environment Variables

- `ARGO_API_URL` - URL of the ARGO Gateway API (default: `https://apps-dev.inside.anl.gov/argoapi/api/v1/resource/chat/`)

## Case Descriptions

| Case | Log File | Description |
|------|----------|-------------|
| 1 | `leaked_tool_20260128_171422_165810.json` | bash tool call with preceding text |
| 2 | `leaked_tool_20260128_171653_513513.json` | task tool call with preceding text |
| 3 | `leaked_tool_20260131_114729_223329.json` | 3 read tool calls in sequence |
| 4 | `leaked_tool_20260131_114941_897350.json` | Pure tool call (no surrounding text) |
| 5 | `leaked_tool_20260131_115028_795330.json` | 4 mixed tool types (read, glob, grep) |

## Expected Output

The scripts output raw JSON responses for analysis. Look for:

### If the bug is reproduced:
- `tool_calls` array is empty
- `content` field contains Python dict format: `{'id': 'toolu_vrtx_...`

### If the bug is NOT reproduced:
- `tool_calls` array contains proper tool call objects
- `content` field contains only text (no embedded tool calls)

## Investigation Status

See `leaked_tool_call_investigation.md` for the full investigation report.