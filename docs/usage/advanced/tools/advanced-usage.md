# Advanced Tool Usage

This guide covers advanced topics and best practices for tool calls (function calling).

## Advanced Tool Design Patterns

### Schema-Only Tools

You can provide tool schemas without actual implementations for various purposes:

```python
# Schema for a "tool" that doesn't actually exist
fake_tool_schema = {
    "type": "function",
    "function": {
        "name": "analyze_user_sentiment",
        "description": "Analyze the emotional tone and sentiment of user messages",
        "parameters": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "The user message to analyze"
                },
                "context": {
                    "type": "string",
                    "description": "Additional context about the conversation"
                }
            },
            "required": ["message"]
        }
    }
}

# When the LLM "calls" this function, you can:
# 1. Return a mock response
# 2. Perform the analysis manually
# 3. Redirect to a different service
# 4. Simply acknowledge the request
```

**Use cases for schema-only tools**:

- **Guided reasoning**: Make the LLM think through problems step-by-step
- **Structured output**: Force the LLM to format responses in specific ways
- **Feature planning**: Test how users would interact with planned features
- **Debugging**: Understand what tools the LLM thinks it needs

### Complex Parameter Schemas

```python
# Advanced parameter validation
{
  "type": "object",
  "properties": {
    "start_date": {
      "type": "string",
      "pattern": "^\\d{4}-\\d{2}-\\d{2}$",
      "description": "Start date in YYYY-MM-DD format"
    },
    "end_date": {
      "type": "string",
      "pattern": "^\\d{4}-\\d{2}-\\d{2}$",
      "description": "End date in YYYY-MM-DD format"
    },
    "metrics": {
      "type": "array",
      "items": {
        "type": "string",
        "enum": ["revenue", "units_sold", "profit_margin", "customer_count"]
      },
      "minItems": 1,
      "maxItems": 4,
      "uniqueItems": true,
      "description": "Which metrics to include in analysis"
    },
    "filters": {
      "type": "object",
      "properties": {
        "region": {
          "type": "string",
          "enum": ["north", "south", "east", "west", "all"]
        },
        "product_category": {
          "type": "array",
          "items": {"type": "string"}
        }
      },
      "additionalProperties": false
    }
  },
  "required": ["start_date", "end_date", "metrics"]
}
```

## Best Practices

### Function Description Guidelines

```python
# ❌ Poor description
def get_data(x):
    """Gets data"""
    pass

# ✅ Good description
def get_weather(location: str, units: str = "metric") -> dict:
    """Get current weather information for a specific location

    Args:
        location: City name or "City, Country" format (e.g., "Tokyo" or "Paris, France")
        units: Temperature units - "metric" for Celsius, "imperial" for Fahrenheit

    Returns:
        Dictionary containing temperature, humidity, conditions, and forecast

    Raises:
        ValueError: If location is not found or invalid
        ConnectionError: If weather service is unavailable
    """
    pass
```

### Error Handling Patterns

```python
def safe_function(user_input: str) -> dict:
    """Example of proper error handling for tool calls"""
    try:
        # Validate input
        if not user_input or len(user_input) > 1000:
            return {
                "error": "Invalid input: must be 1-1000 characters",
                "success": False
            }

        # Process safely
        result = process_input(user_input)

        return {
            "result": result,
            "success": True
        }

    except Exception as e:
        return {
            "error": f"Processing failed: {str(e)}",
            "success": False
        }
```

### Schema Design Rules

```python
# ❌ Vague schema
{
  "name": "process_data",
  "description": "Processes data",
  "parameters": {
    "type": "object",
    "properties": {
      "data": {"type": "string"}
    }
  }
}

# ✅ Clear schema
{
  "name": "analyze_sales_data",
  "description": "Analyze sales performance for a specific time period and generate insights",
  "parameters": {
    "type": "object",
    "properties": {
      "start_date": {
        "type": "string",
        "description": "Start date in YYYY-MM-DD format"
      },
      "end_date": {
        "type": "string",
        "description": "End date in YYYY-MM-DD format"
      },
      "metrics": {
        "type": "array",
        "items": {"type": "string", "enum": ["revenue", "units_sold", "profit_margin"]},
        "description": "Which metrics to include in analysis"
      }
    },
    "required": ["start_date", "end_date"]
  }
}
```

## Security Considerations

### Input Validation

```python
import re
from pathlib import Path

def validate_file_path(file_path: str) -> bool:
    """Validate file path for security"""
    # Check for path traversal attempts
    if ".." in file_path or file_path.startswith("/"):
        return False

    # Ensure it's within allowed directory
    safe_path = Path("./allowed_files") / file_path
    try:
        safe_path.resolve().relative_to(Path("./allowed_files").resolve())
        return True
    except ValueError:
        return False

def secure_file_reader(filename: str) -> dict:
    """Secure file reading function"""
    if not validate_file_path(filename):
        return {"error": "Invalid file path", "success": False}

    try:
        with open(f"./allowed_files/{filename}", 'r') as f:
            content = f.read()
        return {"content": content, "success": True}
    except FileNotFoundError:
        return {"error": "File not found", "success": False}
    except Exception as e:
        return {"error": f"Read error: {str(e)}", "success": False}
```

### Rate Limiting

```python
import time
from collections import defaultdict

class RateLimiter:
    def __init__(self, max_calls=10, time_window=60):
        self.max_calls = max_calls
        self.time_window = time_window
        self.calls = defaultdict(list)

    def is_allowed(self, user_id: str) -> bool:
        now = time.time()
        user_calls = self.calls[user_id]

        # Remove old calls
        user_calls[:] = [call_time for call_time in user_calls
                        if now - call_time < self.time_window]

        if len(user_calls) >= self.max_calls:
            return False

        user_calls.append(now)
        return True

rate_limiter = RateLimiter()

def rate_limited_function(user_id: str, data: str) -> dict:
    """Function with rate limiting"""
    if not rate_limiter.is_allowed(user_id):
        return {"error": "Rate limit exceeded", "success": False}

    # Process the request
    return {"result": f"Processed: {data}", "success": True}
```

## Performance Optimization

### Async Functions

```python
import asyncio
import aiohttp

async def async_weather_function(location: str) -> dict:
    """Async weather function for better performance"""
    async with aiohttp.ClientSession() as session:
        url = f"https://api.weather.com/v1/current?location={location}"
        async with session.get(url) as response:
            data = await response.json()
            return {
                "location": location,
                "temperature": data.get("temperature"),
                "condition": data.get("condition")
            }

# Usage with asyncio
async def execute_async_tools(tool_calls):
    """Execute multiple tool calls concurrently"""
    tasks = []
    for tool_call in tool_calls:
        if tool_call.function.name == "get_weather":
            args = json.loads(tool_call.function.arguments)
            task = async_weather_function(args["location"])
            tasks.append(task)

    results = await asyncio.gather(*tasks)
    return results
```

### Caching

```python
import functools
import time

def timed_cache(seconds: int):
    """Cache with expiration"""
    def decorator(func):
        cache = {}

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            key = str(args) + str(sorted(kwargs.items()))
            now = time.time()

            if key in cache:
                result, timestamp = cache[key]
                if now - timestamp < seconds:
                    return result

            result = func(*args, **kwargs)
            cache[key] = (result, now)
            return result

        return wrapper
    return decorator

@timed_cache(300)  # Cache for 5 minutes
def expensive_calculation(data: str) -> dict:
    """Expensive function with caching"""
    # Simulate expensive operation
    time.sleep(2)
    return {"result": f"Processed {data}", "cached": False}
```

## Real-World Examples

### Weather Service Integration

```python
import requests
from typing import Optional

def get_weather(location: str, units: str = "metric") -> dict:
    """Get weather information for a location"""
    try:
        api_key = "your_api_key"
        url = f"http://api.openweathermap.org/data/2.5/weather"
        params = {
            "q": location,
            "appid": api_key,
            "units": units
        }

        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()

        data = response.json()
        return {
            "location": data["name"],
            "temperature": data["main"]["temp"],
            "condition": data["weather"][0]["description"],
            "humidity": data["main"]["humidity"],
            "success": True
        }
    except requests.RequestException as e:
        return {"error": f"Weather service error: {str(e)}", "success": False}
    except KeyError as e:
        return {"error": f"Invalid response format: {str(e)}", "success": False}
```

### Database Queries

```python
import sqlite3
from typing import List, Dict, Any

def search_database(query: str, table: str, limit: int = 10) -> dict:
    """Search database with SQL query"""
    # Validate table name (whitelist approach)
    allowed_tables = ["products", "customers", "orders"]
    if table not in allowed_tables:
        return {"error": "Table not allowed", "success": False}

    try:
        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()

        # Use parameterized queries for security
        safe_query = f"SELECT * FROM {table} WHERE content LIKE ? LIMIT ?"
        cursor.execute(safe_query, (f"%{query}%", limit))

        results = cursor.fetchall()
        conn.close()

        return {
            "results": results,
            "count": len(results),
            "success": True
        }
    except sqlite3.Error as e:
        return {"error": f"Database error: {str(e)}", "success": False}
```

### API Integrations

```python
import requests
from urllib.parse import urlparse

def call_external_api(endpoint: str, method: str = "GET", data: dict = None) -> dict:
    """Make API calls to external services"""
    # Validate endpoint domain
    allowed_domains = ["api.example.com", "secure-api.service.com"]
    parsed_url = urlparse(endpoint)

    if parsed_url.netloc not in allowed_domains:
        return {"error": "Unauthorized API endpoint", "success": False}

    try:
        if method.upper() == "GET":
            response = requests.get(endpoint, timeout=30)
        elif method.upper() == "POST":
            response = requests.post(endpoint, json=data, timeout=30)
        else:
            return {"error": "Unsupported HTTP method", "success": False}

        response.raise_for_status()
        return {
            "data": response.json(),
            "status_code": response.status_code,
            "success": True
        }
    except requests.RequestException as e:
        return {"error": f"API call failed: {str(e)}", "success": False}
```

## Troubleshooting

### Debug Tips

1. **Enable verbose logging**: Use `--verbose` flag to see detailed logs
2. **Test function schemas**: Validate JSON schema before use
3. **Monitor tool calls**: Log all tool calls and responses
4. **Use simple functions first**: Start with basic functions before complex ones

### Common Patterns

```python
# Debugging tool call execution
def debug_tool_execution(tool_calls):
    """Debug tool call execution"""
    for tool_call in tool_calls:
        print(f"Tool: {tool_call.function.name}")
        print(f"Arguments: {tool_call.function.arguments}")

        try:
            args = json.loads(tool_call.function.arguments)
            result = execute_function(tool_call.function.name, args)
            print(f"Result: {result}")
        except Exception as e:
            print(f"Error: {e}")
```

This advanced guide should help you implement robust and secure tool calling systems.
