#  Git Update: Dynamic Wazuh Rule Synchronization

This document outlines the recent updates made to the Wazuh Rule Distribution (WRD) worker synchronization script (`wrd-sync.sh`).

## What Changed
The primary objective was to modify `wrd-sync.sh` to dynamically fetch all available rules from the GitHub repository, eliminating the need to manually update a hardcoded array of files in the script whenever a new rule is published.

### 1. Replaced Hardcoded Array with Dynamic GitHub API Discovery
**Before:** The script relied on a static list of files:
```bash
RULE_FILES=(
  "local_rules.xml"
  "0200-sigma_rules.xml"
)
```

**After:** We implemented dynamic fetching utilizing the public GitHub repository contents API. The script now reads the JSON response, uses `grep`/`sed` to isolate the filenames, and loops over all files present in the `rules/` directory:
```bash
GITHUB_API="https://api.github.com/repos/${GITHUB_REPO}/contents/${GITHUB_RULES_PATH}?ref=${GITHUB_BRANCH}"

RULE_FILES=$(curl -fsSL "${GITHUB_API}" 2>> "$LOG_FILE" \
  | grep -o '"name": *"[^"]*"' \
  | sed 's/"name": *"//;s/"//')
```

### 2. Repository adjustments
- We initially attempted to point the synchronization to `rise-research-labs/AI_Wazuh`.
- Because that repository is private and the script had no token authentication, we encountered `404 Not Found` API errors.
- We reverted the target repository back to the public `Abhishek-s-kumar/DaC` repository, ensuring the unauthenticated dynamic GitHub API lookups continued to function cleanly.

### 3. Production Deployment & Verification
- The updated script was uploaded to the production server (`10.24.5.111`) via SCP.
- It was correctly copied into the `multi-node-wazuh.worker-1` Docker container at `/usr/local/bin/wrd-sync.sh` and made executable.
- We triggered a complete manual execution of the script inside the container.
- Log verification (`/var/log/wrd-sync.log`) confirmed that:
  - The API list was fetched successfully.
  - The rules were downloaded matching the repository contents.
  - The wazuh-analysisd syntax check completed cleanly (`Exit code 0`).
  - The local Wazuh manager processes restarted properly.
  - The worker correctly reported a `"success"` status back to the WRD API.

## 📌 Future Notes
If you decide to point this integration toward a **private** repository moving forward, a GitHub Personal Access Token (PAT) must be created with read permissions on the repository. The curl initialization line will need to be updated to pass the token as a header: `-H "Authorization: token $GITHUB_TOKEN"`.
