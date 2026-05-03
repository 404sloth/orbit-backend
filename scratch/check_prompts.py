import os

def check_file(path, keywords):
    print(f"Checking {path}...")
    if not os.path.exists(path):
        print(f"  ERROR: File not found at {os.path.abspath(path)}!")
        return
    with open(path, 'r') as f:
        content = f.read()
        for kw in keywords:
            if kw in content:
                print(f"  [OK] Found keyword: '{kw}'")
            else:
                print(f"  [MISSING] Keyword: '{kw}'")

files_to_check = {
    "agents/hybrid.py": ["STRICT TOOL CALLING RULES", "NEVER wrap tool calls in XML-like tags", "NEVER use curly quotes"],
    "agents/knowledge.py": ["STRICT TOOL CALLING RULES", "NEVER wrap tool calls in XML-like tags"],
    "agents/router.py": ["4. report (Executive Report Agent)", "next_node\": \"sql\" | \"rag\" | \"hybrid\" | \"report\""]
}

for path, kws in files_to_check.items():
    check_file(path, kws)
