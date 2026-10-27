from pathlib import Path

path = Path("requirements.txt")
content = path.read_text(encoding="utf-8")

# Reverse the accidental UTF-8/UTF-16LE misinterpretation.
repaired = content.encode("utf-16le").decode("utf-8")

print("Preview of repaired requirements.txt:")
print("\n".join(repaired.splitlines()[:20]))

if input("\nDoes the preview look correct? Type YES to save: ").strip() == "YES":
    backup = Path("requirements.txt.corrupted-backup")
    backup.write_bytes(path.read_bytes())

    path.write_text(repaired, encoding="utf-8", newline="\n")
    print("Repaired requirements.txt and saved a backup.")
else:
    print("No changes made.")