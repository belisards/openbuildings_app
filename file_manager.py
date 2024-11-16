import shutil
from typing import Optional
import gzip
import os


def remove_folder_contents(folder_path):
    # Remove local download folder contents
    for file in os.listdir(folder_path):
        file_path = os.path.join(folder_path, file)
        try:
            if os.path.isfile(file_path):
                os.unlink(file_path)
        except Exception as e:
            print(e)
    
def uncompress(gzipped_file: str, delete_compressed: bool = True) -> Optional[str]:
    """Uncompresses a gzipped CSV file and returns the path to the uncompressed file.

    Args:
        gzipped_file (str): Path to the gzipped CSV file.
        delete_compressed (bool): Whether to delete the compressed file after uncompressing.

    Returns:
        Optional[str]: Path to the uncompressed CSV file if successful, None otherwise.
    """

    try:
        with gzip.open(gzipped_file, 'rb') as gf:
            with open(gzipped_file.replace('.gz', ''), 'wb') as f:
                shutil.copyfileobj(gf, f)

        if delete_compressed:
            os.remove(gzipped_file)

        return gzipped_file.replace('.gz', '')

    except FileNotFoundError:
        return None