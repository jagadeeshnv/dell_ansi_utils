import base64
import tempfile
import os
import requests
import urllib3
from mycreds import gitpat
import subprocess
from pprint import pprint

repo_url = 'https://api.github.com/repos/jagadeeshnv/dell_ansi_utils'
tag_url = f"{repo_url}/commits"
branch_name = 'ansibod_rst_gen'

def get_files_from_commit(commit):
    files = []
    print(commit.get('commit').get('message'))
    # print(commit.get('url'))
    file_resp = requests.get(f"{commit.get('url')}", headers=headers, verify=False)
    file_cont = file_resp.json()
    # pprint(file_cont)
    for f in file_cont.get('files'):
        # print(f.get('filename'))
        files.append(f.get('filename'))
    return files


def download_the_files(modules, branch_name):
    tmp_dir = tempfile.mkdtemp()
    print(tmp_dir)
    temp_docs_dir = f"{tmp_dir}/docs"
    os.mkdir(temp_docs_dir)
    rst_dict = {}
    for mod in modules:
        mod_url = f"{repo_url}/contents/{mod}"
        mod_resp = requests.get(mod_url, params={'ref': branch_name},  headers=headers, verify=False)
        mod_cont = mod_resp.json()
        decoded_data = base64.b64decode(mod_cont.get('content')).decode('utf-8')
        fpath = f"{tmp_dir}/{mod.split('/')[-1]}"
        with open(fpath, 'w') as f:
            f.write(decoded_data)
        result = subprocess.run(["ansible-doc-extractor", temp_docs_dir, fpath], capture_output=True, text=True)
        print(result.stdout)
        rst_dict[mod] = f"docs/{(mod.split('/')[-1]).rstrip('.py')}.rst"
    files = os.listdir(temp_docs_dir)
    full_paths = []
    for file in files:
        file_path = os.path.join(temp_docs_dir, file)
        if os.path.isfile(file_path):
            full_paths.append(file_path)
    return rst_dict, tmp_dir

def get_blobs(rst_dict, tmp_dir):
    blobs = {}
    for gpath, fpath in rst_dict.items():
        payload = {
            "encoding": "utf-8",
            "content": open(f"{tmp_dir}/{fpath}", "r").read()
        }
        blob_resp = requests.post(f"{repo_url}/git/blobs", json=payload, headers=headers, verify=False)
        # pprint(blob_resp.json())
        blobs[fpath] = blob_resp.json().get('sha')
    return blobs

def create_tree(blob_sha_dict, last_commit_sha):
    payload = {
        "base_tree": last_commit_sha,
        "tree": [({"path": k, "mode": "100644", "type": "blob", "sha": v}) for k, v in blob_sha_dict.items()]
    }
    pprint(payload)
    tree_resp = requests.post(f"{repo_url}/git/trees", json=payload, headers=headers, verify=False)
    # pprint(tree_resp.json())
    tree_sha = tree_resp.json()['sha']
    return tree_sha

def create_commit(tree_sha, last_commit_sha):
    payload = {
        "message": "Second attempt to commit",
        "tree": tree_sha,
        "parent": [last_commit_sha]
    }
    commit_resp = requests.post(f"{repo_url}/git/commits", json=payload, headers=headers, verify=False)
    pprint(commit_resp.json())
    commit_sha = commit_resp.json()['sha']
    return commit_sha


urllib3.disable_warnings()
headers = {'Authorization': 'bearer {}'.format(gitpat),
        'Accept': 'application/vnd.github+json'}


response = requests.get(tag_url, params={'sha': branch_name} ,headers=headers, verify=False)
content_data = response.json()
files = get_files_from_commit(content_data[0])
pprint(files)
modified_modules = []
for f in files:
    if f.startswith('plugins/modules/') and f.endswith('.py'):
        modified_modules.append(f)

rst_full_paths_dict, tmp_dir = download_the_files(modified_modules, branch_name)
print(rst_full_paths_dict)

response = requests.get(f"{repo_url}/branches/{branch_name}", headers=headers, verify=False)
last_commit_sha = response.json()['commit']['sha']
print(last_commit_sha)

blob_dict = get_blobs(rst_full_paths_dict, tmp_dir)
pprint(blob_dict)

tree_sha = create_tree(blob_dict, last_commit_sha)
print(tree_sha)

new_commit_sha = create_commit(tree_sha, last_commit_sha)
print(new_commit_sha)

# update_commit = f"{repo_url}/git/commits/{new_commit_sha}"
# PATCH /repos/:owner/:repo/git/refs/heads/:branch
# {
#     "sha": new_commit_sha
# }

update_ref_payload = {
    "sha": new_commit_sha,
    "force": True
}
response = requests.patch(f"{repo_url}/git/refs/heads/{branch_name}", json=update_ref_payload, headers=headers, verify=False)
print(response.json())
