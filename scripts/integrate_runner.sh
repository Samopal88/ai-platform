#!/bin/bash
# Script to integrate runner_router into live backend
# Run this script in /opt/ai-workspace/backend directory

# Copy runner_router.py
cp /opt/ai-workspace/storage/projects/ai-platform/backend/runner_router.py /opt/ai-workspace/backend/runner_router.py

# Backup existing main.py
cp /opt/ai-workspace/backend/main.py /opt/ai-workspace/backend/main.py.backup

# Update main.py to include runner router
python3 << 'EOF'
import re

# Read current main.py
with open('/opt/ai-workspace/backend/main.py', 'r') as f:
    content = f.read()

# Check if runner_router is already imported
if 'runner_router' in content:
    print('runner_router already imported')
    exit(0)

# Add import after other imports
import_line = 'from runner_router import router as runner_router'

# Find position after orchestrator_lib import
pos = content.find('from orchestrator_lib import')
if pos != -1:
    # Find end of this import block
    end_import = content.find('\n\n', pos)
    if end_import != -1:
        content = content[:end_import] + '\n\n# Import runner router\n' + import_line + content[end_import:]

# Add router include after app creation
app_include = 'app.include_router(runner_router)'
app_pos = content.find('app = FastAPI')
if app_pos != -1:
    # Find next line
    newline_pos = content.find('\n', app_pos)
    if newline_pos != -1:
        content = content[:newline_pos+1] + '\n# Include runner router\n' + app_include + '\n' + content[newline_pos+1:]

# Write updated main.py
with open('/opt/ai-workspace/backend/main.py', 'w') as f:
    f.write(content)

print('main.py updated successfully')
EOF

echo "Integration complete. Restart the backend to apply changes:"
echo "sudo systemctl restart ai-workspace-backend"
