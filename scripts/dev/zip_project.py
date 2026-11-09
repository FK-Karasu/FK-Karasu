import zipfile
import os

def zip_project(source_dir, output_filename):
    print(f"Archiving {source_dir} to {output_filename}...")
    
    # Files/Dirs to exclude
    EXCLUDES = {
        'venv_win', 
        '__pycache__', 
        '.git', 
        '.vscode', 
        'football_school_ready.zip',
        'zip_project.py',
        '.DS_Store'
    }

    with zipfile.ZipFile(output_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(source_dir):
            # Modify dirs in-place to skip excluded directories
            dirs[:] = [d for d in dirs if d not in EXCLUDES]
            
            for file in files:
                if file in EXCLUDES:
                    continue
                if file.endswith('.pyc'): # Skip compiled python files
                    continue
                    
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, source_dir)
                
                try:
                    print(f"Adding {arcname}")
                    zipf.write(file_path, arcname)
                except PermissionError:
                    print(f"WARNING: Could not access {file_path}. Skipping.")
                except Exception as e:
                    print(f"ERROR adding {file_path}: {e}")

    print("Success! Archive created.")

if __name__ == "__main__":
    # Source is current directory
    source = os.getcwd()
    # Destination is Desktop
    desktop = os.path.join(os.environ['USERPROFILE'], 'Desktop')
    destination = os.path.join(desktop, 'football_school_ready.zip')
    
    zip_project(source, destination)
