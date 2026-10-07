# Repo manifest sources

Use an existing git-repo XML manifest without listing its projects again in MB.
Install the repo launcher and its Git/Python prerequisites through your site's
normal process; MB uses repo and git on PATH and does not install them.

Copy examples/repo-sources.yaml and replace the manifest repository URL.
The source fields are:

| Field | Meaning |
| --- | --- |
| provider: repo | Use git-repo |
| name | Directory below workspace/sources |
| url | Git repository containing the XML, not an individual XML file |
| revision | Manifest branch/revision; default HEAD |
| config.manifest | XML within the manifest repository; default default.xml |

Project revisions and paths remain owned by the XML. Other repo-specific config
fields are rejected. Run mb prepare my-run.yaml. Initial acquisition invokes:

    repo init -u ssh://SERVER/manifests.git -b main -m default.xml
    repo sync -j 1

Commands run inside a new temporary sibling directory. On success the complete
tree is moved to <workspace>/sources/platform/. A failed initial acquisition
removes only this new temporary tree; fix the cause and repeat prepare.
Existing destination files are never removed. Avoid editing the temporary
directory during acquisition. Output is displayed live on stderr, preserving
MB JSON stdout.

An existing .repo tree is reused without init, sync, reset, or cleanup.
Local edits and branches remain user-managed. To update explicitly:

    cd work/repo-example/sources/platform
    repo status
    repo sync -j 1

Review your changes first: sync is a normal project update and may require
resolving conflicts. Repeating MB prepare does not perform this update.
An existing partially synced tree created outside MB is also user-managed;
complete or repair it using repo before use.

Evidence records the manifest repository's local HEAD only. It is not a snapshot
of every project revision, local manifest, or working-tree edit. On reuse the
requested URL, revision and XML remain configuration intent. Doctor checks
executable availability and config, but does not init a tree or contact projects.

The launcher may download git-repo itself during init in addition to your
manifest/projects. Use your site's normal repo configuration (including
REPO_URL/REPO_REV where needed); PATH availability alone does not establish
network access or credentials. MB does not add force-sync options.

References:
- [repo init](https://gerrit.googlesource.com/git-repo/+/HEAD/man/repo-init.1)
- [repo sync](https://gerrit.googlesource.com/git-repo/+/HEAD/man/repo-sync.1)

## Validation scope

Automated provider tests cover command arguments, failure cleanup, repeat attempts,
existing-tree preservation, invalid config, and missing executables. They use a
controlled command substitute and require no repo installation or network.
A smoke attempt with the official git-repo implementation completed init, but
sync was blocked by this test environment's prohibition on local sockets used
by Python multiprocessing. End-to-end sync and relocation therefore still need
confirmation in an environment where git-repo can run normally.
