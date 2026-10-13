import os

directory = '/home/nikita/Desktop/Projects/inventory management billing system/msme-paytrack/backend/apps'
for root, dirs, files in os.walk(directory):
    for file in files:
        if file.endswith('.py'):
            filepath = os.path.join(root, file)
            with open(filepath, 'r') as f:
                content = f.read()
            
            # Use string replacement for exact matches
            new_content = content.replace("request.user.role_name == 'EMPLOYEE'", "request.user.role_name in ['EMPLOYEE', 'USER']")
            new_content = new_content.replace("self.request.user.role_name == 'EMPLOYEE'", "self.request.user.role_name in ['EMPLOYEE', 'USER']")
            
            if new_content != content:
                with open(filepath, 'w') as f:
                    f.write(new_content)
                print(f"Patched {filepath}")
