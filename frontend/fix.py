import os

src_dir = r"c:\Users\Modmin\Desktop\broadcaster\frontend\src"

for root, dirs, files in os.walk(src_dir):
    for f in files:
        if f.endswith(('.tsx', '.ts')):
            filepath = os.path.join(root, f)
            with open(filepath, 'r', encoding='utf-8') as file:
                content = file.read()
            
            new_content = content.replace("'http://localhost:8000/api/v1", "(process.env.INTERNAL_API_URL || '/api/v1') + '")
            new_content = new_content.replace("`http://localhost:8000/api/v1", "`${process.env.INTERNAL_API_URL || '/api/v1'}")
            new_content = new_content.replace('"http://localhost:8000/api/v1"', "(process.env.INTERNAL_API_URL || '/api/v1')")

            if new_content != content:
                with open(filepath, 'w', encoding='utf-8') as file:
                    file.write(new_content)
                print(f'Updated {f}')
