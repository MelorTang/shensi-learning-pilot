# Curriculum Knowledge Source

This directory stores committed, non-personal curriculum knowledge cards.

Put reviewed Markdown cards under subject folders, for example:

```text
knowledge/curriculum/数学/一元一次方程.md
knowledge/curriculum/数学/一次函数求值.md
```

Run this after `git pull` on the cloud server:

```bash
python scripts/sync_curriculum.py
```

Files named `README.md` or starting with `_` are skipped by the sync script.

