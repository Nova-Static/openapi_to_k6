# OpenAPI to k6 Load Test Generator

A smart tool that converts OpenAPI specifications into k6 load test scripts with intelligent features:

- **Authorization handling**: Automatically injects authorization headers (except for `/admin` endpoints)
- **Dynamic value tracking**: Tracks IDs from responses (e.g., franchise IDs) and uses them in subsequent requests
- **Path parameter replacement**: Automatically replaces path parameters like `/franchise/{franchiseId}` with tracked values
- **Admin endpoint filtering**: Automatically excludes `/admin` paths from the generated tests

## Installation

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Install k6 (if not already installed):
```bash
# On macOS
brew install k6

# On Linux
sudo gpg -k
sudo gpg --no-default-keyring --keyring /usr/share/keyrings/k6-archive-keyring.gpg --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys C5AD17C747E3415A3642D57D77C6C491D6AC1D53
echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main" | sudo tee /etc/apt/sources.list.d/k6.list
sudo apt-get update
sudo apt-get install k6

# Or download from https://k6.io/docs/getting-started/installation/
```

## Usage

### Basic Usage

```bash
python openapi_to_k6.py -i api.yaml -o test.js
```

### With Authorization Key

```bash
python openapi_to_k6.py -i api.yaml -o test.js --auth-key "your-api-key"
```

### Running the Generated Test

```bash
# Set authorization key and base URL via environment variables
k6 run test.js -e AUTH_KEY="your-api-key" -e BASE_URL="https://api.example.com"

# Or use the auth key from the command line argument
k6 run test.js -e BASE_URL="https://api.example.com"
```

## Features

### Smart Authorization

The tool automatically adds authorization headers to all requests except those to `/admin` endpoints. You can provide the auth key either:
- Via the `--auth-key` command line argument
- Via the `AUTH_KEY` environment variable when running k6

### Dynamic Value Tracking

When a request creates a resource (e.g., `POST /franchise`), the tool automatically:
1. Extracts the ID from the response (checks for `id`, `franchiseId`, etc.)
2. Stores it in a shared state object
3. Uses it in subsequent requests that need it (e.g., `GET /franchise/{franchiseId}`)

### Path Parameter Replacement

Path parameters like `/franchise/{franchiseId}` are automatically replaced with:
1. Tracked values from previous responses (if available)
2. Fallback to the parameter name if no tracked value exists

### Admin Endpoint Filtering

All endpoints containing `/admin` in their path are automatically excluded from the generated test.

## Example

Given an OpenAPI spec with:
- `POST /franchise` - Creates a franchise, returns `{ "id": "123" }`
- `GET /franchise/{franchiseId}` - Gets a franchise by ID
- `GET /admin/users` - Admin endpoint (excluded)

The generated k6 script will:
1. Call `POST /franchise` and track the returned ID
2. Use that ID in `GET /franchise/{franchiseId}`
3. Skip `GET /admin/users` entirely

## Customization

You can customize the generated k6 script by editing the `options` object in the generated file:
- Adjust load test stages (ramp-up, duration, ramp-down)
- Modify thresholds (response time, error rate)
- Change request order or add custom logic

## Requirements

- Python 3.7+
- k6 (latest version recommended)
- PyYAML (for parsing YAML OpenAPI specs)

## License

MIT

