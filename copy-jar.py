import os

# Base path where JetBrains products are installed
base_path = r"C:\Users\varad\AppData\Local\Programs"

# The correct agent line
agent_line = "-javaagent:C:\\temp\\sniarbtej.jar=id=sniarbtej,user=Varadhaajan,exp=2098-10-24,force=true"

# Keywords that identify JetBrains IDEs
jetbrains_keywords = ["pycharm", "intellij", "datagrip", "dataspell", "goland", "rider",
                      "rubymine", "phpstorm", "webstorm", "clion", "appcode", "jetbrains"]

# Detect only JetBrains product folders
for folder in os.listdir(base_path):
    folder_path = os.path.join(base_path, folder)
    if not os.path.isdir(folder_path):
        continue

    # Skip non-JetBrains folders
    if not any(keyword.lower() in folder.lower() for keyword in jetbrains_keywords):
        continue

    bin_path = os.path.join(folder_path, "bin")
    if not os.path.exists(bin_path):
        continue

    for filename in os.listdir(bin_path):
        if filename.endswith(".exe.vmoptions"):
            file_path = os.path.join(bin_path, filename)
            print(f"Processing {file_path}...")

            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
            except FileNotFoundError:
                print(f"⚠️  File not found: {file_path}")
                continue

            found = False
            for i, line in enumerate(lines):
                if "sniarbtej.jar" in line:
                    lines[i] = agent_line + "\n"
                    found = True
                    print(f"  → Replaced existing agent line")
                    break

            if not found:
                lines.append(agent_line + "\n")
                print(f"  → Appended new agent line")

            with open(file_path, "w", encoding="utf-8") as f:
                f.writelines(lines)

            print(f"✅ Updated {file_path}\n")
