use std::ffi::OsString;
use std::path::{Path, PathBuf};

fn executable_names(command: &str) -> Vec<String> {
    let path = Path::new(command);
    if path.extension().is_some() || !cfg!(windows) {
        return vec![command.to_string()];
    }
    vec![format!("{command}.exe"), command.to_string()]
}

fn find_in_directories(
    command: &str,
    directories: impl IntoIterator<Item = PathBuf>,
) -> Option<PathBuf> {
    let names = executable_names(command);
    for directory in directories {
        for name in &names {
            let candidate = directory.join(name);
            if candidate.is_file() {
                return candidate.canonicalize().ok().or(Some(candidate));
            }
        }
    }
    None
}

fn platform_directories() -> Vec<PathBuf> {
    #[cfg(target_os = "macos")]
    {
        let mut directories: Vec<PathBuf> = [
            "/opt/homebrew/bin",
            "/usr/local/bin",
            "/opt/local/bin",
            "/usr/bin",
            "/bin",
        ]
        .into_iter()
        .map(PathBuf::from)
        .collect();
        if let Some(home) = dirs::home_dir() {
            directories.push(home.join(".local/bin"));
            let python_root = home.join("Library/Python");
            if let Ok(entries) = std::fs::read_dir(python_root) {
                directories.extend(
                    entries
                        .filter_map(Result::ok)
                        .map(|entry| entry.path().join("bin")),
                );
            }
        }
        return directories;
    }

    #[cfg(windows)]
    {
        let mut directories = Vec::new();
        if let Some(value) = std::env::var_os("LOCALAPPDATA") {
            let root = PathBuf::from(value);
            directories.push(root.join("Microsoft/WinGet/Links"));
            directories.push(root.join("Programs/GitHub CLI"));
            directories.push(root.join("Programs/yt-dlp"));
        }
        if let Some(value) = std::env::var_os("ProgramFiles") {
            let root = PathBuf::from(value);
            directories.push(root.join("Git/cmd"));
            directories.push(root.join("Git/bin"));
            directories.push(root.join("GitHub CLI"));
            directories.push(root.join("ffmpeg/bin"));
        }
        if let Some(value) = std::env::var_os("ChocolateyInstall") {
            directories.push(PathBuf::from(value).join("bin"));
        }
        if let Some(value) = std::env::var_os("USERPROFILE") {
            directories.push(PathBuf::from(value).join("scoop/shims"));
        }
        return directories;
    }

    #[cfg(all(unix, not(target_os = "macos")))]
    {
        ["/usr/local/bin", "/usr/bin", "/bin"]
            .into_iter()
            .map(PathBuf::from)
            .collect()
    }
}

pub fn resolve_executable(command: &str) -> Option<PathBuf> {
    let supplied = Path::new(command);
    if supplied.components().count() > 1 && supplied.is_file() {
        return supplied
            .canonicalize()
            .ok()
            .or_else(|| Some(supplied.to_path_buf()));
    }

    if let Some(path) = std::env::var_os("PATH") {
        if let Some(found) = find_in_directories(command, std::env::split_paths(&path)) {
            return Some(found);
        }
    }
    find_in_directories(command, platform_directories())
}

pub fn require_executable(command: &str) -> Result<PathBuf, String> {
    resolve_executable(command).ok_or_else(|| {
        format!("找不到 {command}。请安装后重新运行系统诊断；桌面端已检查 PATH 和常见安装目录")
    })
}

/// Finder-launched macOS apps do not inherit the user's shell PATH.  Preserve
/// known tool locations so Python wrappers such as mlx_whisper can invoke
/// ffmpeg internally after the desktop app has resolved it successfully.
pub fn child_process_path() -> OsString {
    let mut directories = platform_directories();
    if let Some(path) = std::env::var_os("PATH") {
        directories.extend(std::env::split_paths(&path));
    }
    directories.sort();
    directories.dedup();
    std::env::join_paths(directories).unwrap_or_else(|_| OsString::new())
}

pub fn resolve_browser_executable() -> Option<PathBuf> {
    #[cfg(target_os = "macos")]
    {
        for path in [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ] {
            let path = PathBuf::from(path);
            if path.is_file() {
                return Some(path);
            }
        }
    }

    #[cfg(windows)]
    {
        let roots = [
            std::env::var_os("LOCALAPPDATA"),
            std::env::var_os("ProgramFiles"),
            std::env::var_os("ProgramFiles(x86)"),
        ];
        for root in roots.into_iter().flatten().map(PathBuf::from) {
            for suffix in [
                "Google/Chrome/Application/chrome.exe",
                "Microsoft/Edge/Application/msedge.exe",
                "Chromium/Application/chrome.exe",
            ] {
                let path = root.join(suffix);
                if path.is_file() {
                    return Some(path);
                }
            }
        }
    }

    [
        "google-chrome",
        "chrome",
        "chromium",
        "chromium-browser",
        "msedge",
    ]
    .into_iter()
    .find_map(resolve_executable)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn resolves_a_file_from_an_explicit_directory() {
        let temp = tempfile::tempdir().unwrap();
        let file_name = if cfg!(windows) {
            "ffmpeg.exe"
        } else {
            "ffmpeg"
        };
        let executable = temp.path().join(file_name);
        std::fs::write(&executable, b"test").unwrap();

        let resolved = find_in_directories("ffmpeg", [temp.path().to_path_buf()]).unwrap();
        assert_eq!(resolved, executable.canonicalize().unwrap());
    }

    #[test]
    fn missing_executable_has_an_actionable_error() {
        let error = require_executable("definitely-not-a-real-workbench-tool").unwrap_err();
        assert!(error.contains("常见安装目录"));
    }

    #[test]
    fn browser_resolution_never_returns_a_missing_path() {
        assert!(resolve_browser_executable().is_none_or(|path| path.is_file()));
    }

    #[test]
    fn child_process_path_includes_platform_tool_directories() {
        let path = child_process_path();
        assert!(!path.is_empty());
        let directories = std::env::split_paths(&path).collect::<Vec<_>>();
        assert!(platform_directories()
            .iter()
            .any(|directory| directories.contains(directory)));
    }
}
