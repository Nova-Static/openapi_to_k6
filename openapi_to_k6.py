#!/usr/bin/env python3
"""
OpenAPI to k6 Load Test Generator

This tool takes an OpenAPI specification and generates a k6 load test script
with smart features:
- Authorization header injection (except for /admin endpoints)
- Dynamic value tracking (e.g., franchise IDs from responses)
- Automatic path parameter replacement
"""

import json
import yaml
import argparse
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional, Set
from urllib.parse import urlparse
import re


class OpenAPIToK6:
    def __init__(self, openapi_spec: Dict[str, Any], auth_key: Optional[str] = None):
        self.spec = openapi_spec
        self.auth_key = auth_key
        self.tracked_values: Dict[str, Any] = {}
        self.endpoints: List[Dict[str, Any]] = []
        
    def parse_spec(self):
        """Parse OpenAPI spec and extract endpoints, filtering out /admin paths"""
        paths = self.spec.get('paths', {})
        base_url = self.spec.get('servers', [{}])[0].get('url', 'http://localhost')
        
        for path, path_item in paths.items():
            # Skip /admin endpoints
            if '/admin' in path:
                continue
                
            # Extract all HTTP methods for this path
            for method, operation in path_item.items():
                if method.lower() in ['get', 'post', 'put', 'patch', 'delete', 'head', 'options']:
                    endpoint = {
                        'path': path,
                        'method': method.upper(),
                        'operation': operation,
                        'operation_id': operation.get('operationId', f'{method}_{path.replace("/", "_").replace("{", "").replace("}", "")}'),
                        'base_url': base_url
                    }
                    self.endpoints.append(endpoint)
    
    def extract_path_parameters(self, path: str) -> List[str]:
        """Extract path parameters from a path string"""
        return re.findall(r'\{(\w+)\}', path)
    
    def find_response_value_extractor(self, operation: Dict[str, Any], param_name: str) -> Optional[str]:
        """Find the JSONPath or field name to extract from response"""
        responses = operation.get('responses', {})
        
        # Check 200, 201, 202 responses first
        for status_code in ['200', '201', '202', 'default']:
            response = responses.get(status_code, {})
            content = response.get('content', {})
            
            # Check JSON schema
            for content_type, media_type in content.items():
                if 'json' in content_type.lower():
                    schema = media_type.get('schema', {})
                    
                    # Check if response has the parameter name as a property
                    properties = schema.get('properties', {})
                    if param_name in properties:
                        return f'json.{param_name}'
                    
                    # Check if it's an object with an id field
                    if 'id' in properties:
                        return 'json.id'
                    
                    # Check for common patterns
                    if schema.get('type') == 'object':
                        # Try to find id-like fields
                        for prop_name, prop_schema in properties.items():
                            if 'id' in prop_name.lower():
                                return f'json.{prop_name}'
        
        return None
    
    def generate_value_tracker(self, path: str, operation: Dict[str, Any], res_var: str) -> str:
        """Generate JavaScript code to track values from responses"""
        path_params = self.extract_path_parameters(path)
        trackers = []
        
        # Check if this is a POST/PUT that might create a resource
        method = operation.get('method', '').upper()
        if method in ['POST', 'PUT']:
            # Look for common ID patterns in path parameters
            for param in path_params:
                if 'id' in param.lower() or 'franchise' in param.lower():
                    extractor = self.find_response_value_extractor(operation, param)
                    if extractor:
                        trackers.append(f"""
        try {{
            if ({res_var}.status === 201 || {res_var}.status === 200) {{
                const json = {res_var}.json();
                const value = json.{extractor.split('.')[1] if '.' in extractor else extractor};
                if (value) {{
                    trackedValues['{param}'] = value;
                    console.log(`Tracked {param}: ${{value}}`);
                }}
            }}
        }} catch (e) {{
            // Response might not be JSON
        }}""")
        
        # Also check response body for franchise creation
        if 'franchise' in path.lower() and method == 'POST':
            trackers.append(f"""
        try {{
            if ({res_var}.status === 201 || {res_var}.status === 200) {{
                const body = {res_var}.json();
                if (body && body.id) {{
                    trackedValues['franchiseId'] = body.id;
                    console.log(`Tracked franchiseId: ${{body.id}}`);
                }} else if (body && body.franchiseId) {{
                    trackedValues['franchiseId'] = body.franchiseId;
                    console.log(`Tracked franchiseId: ${{body.franchiseId}}`);
                }}
            }}
        }} catch (e) {{
            // Response might not be JSON
        }}""")
        
        return '\n'.join(trackers)
    
    def replace_path_parameters(self, path: str) -> str:
        """Replace path parameters with tracked values or placeholders"""
        path_params = self.extract_path_parameters(path)
        result = path
        
        for param in path_params:
            # Try to find a tracked value - check exact match, then lowercase variation
            replacement = f"trackedValues.{param} || trackedValues.{param.lower()} || '{param}'"
            result = result.replace(f'{{{param}}}', f'${{{replacement}}}')
        
        return result
    
    def generate_k6_script(self) -> str:
        """Generate the k6 test script"""
        script_parts = [
            "import http from 'k6/http';",
            "import { check, sleep } from 'k6';",
            "import { Rate } from 'k6/metrics';",
            "",
            "// Error rate metric",
            "const errorRate = new Rate('errors');",
            "",
            "// Shared state for tracked values across VUs",
            "const trackedValues = {};",
            "",
            "export const options = {",
            "    stages: [",
            "        { duration: '30s', target: 10 },  // Ramp up",
            "        { duration: '1m', target: 10 },   // Stay at 10 users",
            "        { duration: '30s', target: 0 },   // Ramp down",
            "    ],",
            "    thresholds: {",
            "        'http_req_duration': ['p(95)<500'],",
            "        'errors': ['rate<0.1'],",
            "    },",
            "};",
            "",
            "export default function () {",
            "    const baseUrl = __ENV.BASE_URL || '" + (self.spec.get('servers', [{}])[0].get('url', 'http://localhost')) + "';",
            "    const authKey = __ENV.AUTH_KEY || null;",
            "",
        ]
        
        # Generate test cases for each endpoint
        for i, endpoint in enumerate(self.endpoints):
            path = endpoint['path']
            method = endpoint['method']
            operation_id = endpoint['operation_id']
            
            # Replace path parameters
            resolved_path = self.replace_path_parameters(path)
            
            # Build URL
            url_code = f"    const url{i} = baseUrl + `{resolved_path}`;"
            
            # Build headers
            headers_code = ["    const headers" + str(i) + " = {"]
            headers_code.append("        'Content-Type': 'application/json',")
            
            # Add auth header if not /admin (always allow runtime auth key)
            if '/admin' not in path:
                headers_code.append("        ...(authKey ? { 'Authorization': `Bearer ${authKey}` } : {}),")
            
            headers_code.append("    };")
            
            # Build request body (if needed)
            request_body_var = ""
            request_body_code = ""
            operation = endpoint['operation']
            if method in ['POST', 'PUT', 'PATCH']:
                request_body_schema = operation.get('requestBody', {}).get('content', {}).get('application/json', {}).get('schema', {})
                if not request_body_schema:
                    # Try other content types
                    for content_type, media_type in operation.get('requestBody', {}).get('content', {}).items():
                        if 'json' in content_type.lower():
                            request_body_schema = media_type.get('schema', {})
                            break
                
                if request_body_schema:
                    # Generate a minimal request body based on schema
                    body_var_name = f"body{i}"
                    request_body_code = self.generate_request_body(request_body_schema, body_var_name)
                    request_body_var = body_var_name
            
            # Generate value tracker
            res_var = f"res{i}"
            tracker_code = self.generate_value_tracker(path, {**operation, 'method': method}, res_var)
            
            # Build the request
            if request_body_var:
                request_code = f"""
    const res{i} = http.{method.lower()}(url{i}, JSON.stringify({request_body_var}), {{ headers: headers{i} }});"""
            else:
                request_code = f"""
    const res{i} = http.{method.lower()}(url{i}, null, {{ headers: headers{i} }});"""
            
            # Add checks and tracking
            check_code = f"""
    const success{i} = check(res{i}, {{
        'status is 2xx or 3xx': (r) => r.status >= 200 && r.status < 400,
    }});
    errorRate.add(!success{i});"""
            
            script_parts.extend([
                "",
                f"    // {operation_id}: {method} {path}",
                url_code,
                *headers_code,
                request_body_code if request_body_code else "",
                request_code,
                check_code,
                tracker_code,
            ])
        
        script_parts.extend([
            "",
            "    // Small sleep between requests",
            "    sleep(0.5);",
            "}",
        ])
        
        return '\n'.join(script_parts)
    
    def generate_request_body(self, schema: Dict[str, Any], var_name: str) -> str:
        """Generate a sample request body based on schema"""
        properties = schema.get('properties', {})
        required = schema.get('required', [])
        
        body_parts = []
        for prop_name, prop_schema in properties.items():
            prop_type = prop_schema.get('type', 'string')
            default_value = prop_schema.get('default')
            
            if default_value is not None:
                if isinstance(default_value, str):
                    body_parts.append(f"        {prop_name}: '{default_value}'")
                else:
                    body_parts.append(f"        {prop_name}: {default_value}")
            elif prop_type == 'string':
                # Use tracked values if available
                if 'id' in prop_name.lower() or 'franchise' in prop_name.lower():
                    body_parts.append(f"        {prop_name}: trackedValues.{prop_name} || trackedValues.franchiseId || '{prop_name}_value'")
                else:
                    body_parts.append(f"        {prop_name}: '{prop_name}_value'")
            elif prop_type == 'integer' or prop_type == 'number':
                body_parts.append(f"        {prop_name}: {prop_schema.get('default', 0)}")
            elif prop_type == 'boolean':
                body_parts.append(f"        {prop_name}: {prop_schema.get('default', False)}")
            elif prop_type == 'array':
                body_parts.append(f"        {prop_name}: []")
            elif prop_type == 'object':
                body_parts.append(f"        {prop_name}: {{}}")
        
        if body_parts:
            return f"    const {var_name} = {{\n" + ",\n".join(body_parts) + "\n    };"
        return ""
    
    def generate(self) -> str:
        """Main method to generate k6 script"""
        self.parse_spec()
        return self.generate_k6_script()


def load_openapi_spec(file_path: str) -> Dict[str, Any]:
    """Load OpenAPI spec from YAML or JSON file"""
    path = Path(file_path)
    
    if not path.exists():
        raise FileNotFoundError(f"OpenAPI spec file not found: {file_path}")
    
    with open(path, 'r') as f:
        if path.suffix in ['.yaml', '.yml']:
            return yaml.safe_load(f)
        elif path.suffix == '.json':
            return json.load(f)
        else:
            # Try JSON first, then YAML
            try:
                content = f.read()
                return json.loads(content)
            except json.JSONDecodeError:
                f.seek(0)
                return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser(
        description='Generate k6 load test script from OpenAPI specification',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage
  python openapi_to_k6.py -i api.yaml -o test.js
  
  # With authorization key
  python openapi_to_k6.py -i api.yaml -o test.js --auth-key "your-api-key"
  
  # Run the generated test
  k6 run test.js -e AUTH_KEY="your-api-key" -e BASE_URL="https://api.example.com"
        """
    )
    
    parser.add_argument('-i', '--input', required=True, help='Input OpenAPI spec file (YAML or JSON)')
    parser.add_argument('-o', '--output', required=True, help='Output k6 test script file')
    parser.add_argument('--auth-key', help='Authorization key to use in requests (can also be set via AUTH_KEY env var)')
    
    args = parser.parse_args()
    
    try:
        # Load OpenAPI spec
        print(f"Loading OpenAPI spec from {args.input}...")
        spec = load_openapi_spec(args.input)
        
        # Get auth key from args or environment
        auth_key = args.auth_key or None
        
        # Generate k6 script
        print("Generating k6 test script...")
        generator = OpenAPIToK6(spec, auth_key)
        k6_script = generator.generate()
        
        # Write output
        output_path = Path(args.output)
        output_path.write_text(k6_script)
        print(f"✓ Generated k6 test script: {args.output}")
        print(f"  Found {len(generator.endpoints)} endpoints (excluding /admin paths)")
        
        print("\nTo run the test:")
        print(f"  k6 run {args.output} -e AUTH_KEY='your-key' -e BASE_URL='https://api.example.com'")
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()

