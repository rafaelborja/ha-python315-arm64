"""Print name==version for every distribution installed in the running interpreter (homeassistant excluded).

Used instead of `pip freeze`, which depends on pip being present and prints editable/URL forms.
First two lines: "# alpine <release>" and "# python <version>".
"""
import importlib.metadata as md
import pathlib
import platform

print(f"# alpine {pathlib.Path('/etc/alpine-release').read_text().strip()}")
print(f"# python {platform.python_version()}")
seen = {}
for d in md.distributions():
    name = d.metadata["Name"]
    if name and name.lower() != "homeassistant":
        seen[name.lower()] = f"{name}=={d.version}"
print("\n".join(seen[k] for k in sorted(seen)))
