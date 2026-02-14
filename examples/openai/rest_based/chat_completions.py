import json
import os

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("BASE_URL", "http://localhost:44498")
MODEL = os.getenv("MODEL", "argo:gpt-4o")

CHAT_ENDPOINT = f"{BASE_URL}/v1/chat/completions"

print("Running Chat Test with Messages")

# Define the request payload using the "messages" field
# payload = {
#     "model": MODEL,
#     "messages": [
#         {
#             "role": "user",
#             "content": "Tell me something interesting about quantum mechanics.",
#         },
#     ],
#     "user": "test_user",  # This will be overridden by the proxy_request function
#     # "max_tokens": 5,
# }
payload = {
    "messages": [
        {
            "role": "system",
            "content": '<important_rules>\n  You are in chat mode.\n\n  If the user asks to make changes to files offer that they can use the Apply Button on the code block, or switch to Agent Mode to make the suggested updates automatically.\n  If needed consisely explain to the user they can switch to agent mode using the Mode Selector dropdown and provide no other details.\n\n  Always include the language and file name in the info string when you write code blocks.\n  If you are editing "src/main.py" for example, your code block should start with \'```python src/main.py\'\n\n  When addressing code modification requests, present a concise code snippet that\n  emphasizes only the necessary changes and uses abbreviated placeholders for\n  unmodified sections. For example:\n\n  ```language /path/to/file\n  // ... existing code ...\n\n  {{ modified code here }}\n\n  // ... existing code ...\n\n  {{ another modification }}\n\n  // ... rest of code ...\n  ```\n\n  In existing files, you should always restate the function or class that the snippet belongs to:\n\n  ```language /path/to/file\n  // ... existing code ...\n\n  function exampleFunction() {\n    // ... existing code ...\n\n    {{ modified code here }}\n\n    // ... rest of function ...\n  }\n\n  // ... rest of code ...\n  ```\n\n  Since users have access to their complete file, they prefer reading only the\n  relevant modifications. It\'s perfectly acceptable to omit unmodified portions\n  at the beginning, middle, or end of files using these "lazy" comments. Only\n  provide the complete file when explicitly requested. Include a concise explanation\n  of changes unless the user specifically asks for code only.\n\n</important_rules>',
        },
        {
            "role": "user",
            "content": "\n\n```py src/argoproxy/models.py (59-74)\n# any models that unable to handle system prompt\nNO_SYS_MSG_PATTERNS = {\n    \"argo:gpt-o1-*\",  # Matches any model name starting with 'argo:gpt-o'\n    \"argo:o1-*\",  # Matches any model name starting with 'argo:o'\n    \"gpto1*\",  # Matches any model name starting with 'gpto'\n}\n\nNO_SYS_MSG = [\n    model\n    for model in CHAT_MODELS\n    if any(fnmatch.fnmatch(model, pattern) for pattern in NO_SYS_MSG_PATTERNS)\n] + [\n    short_name\n    for short_name in _CHAT_MODELS.keys()\n    if any(fnmatch.fnmatch(short_name, pattern) for pattern in NO_SYS_MSG_PATTERNS)\n]\n```\nI want gpto1preview and gpto1mini be captured, but not gpto",
        },
    ],
    "model": MODEL,
    "max_tokens": 4096,
    "stream": False,
}
headers = {
    "Content-Type": "application/json",
}

# Send the POST request
response = requests.post(CHAT_ENDPOINT, headers=headers, json=payload)

try:
    response.raise_for_status()
    print("Response Status Code:", response.status_code)
    print(response.text)
    print("Response Body:", json.dumps(response.json(), indent=4))
except requests.exceptions.HTTPError as err:
    print("HTTP Error:", err)
    print("Response Body:", response.text)
