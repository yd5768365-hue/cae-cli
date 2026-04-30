use tauri_plugin_shell::ShellExt;
use tauri_plugin_dialog::DialogExt;
use std::path::PathBuf;

#[tauri::command]
async fn pick_inp_file(app: tauri::AppHandle, start_dir: Option<String>) -> Option<String> {
    let mut dialog = app
        .dialog()
        .file()
        .set_title("选择 INP 文件")
        .add_filter("INP 输入文件", &["inp"]);

    if let Some(dir) = start_dir {
        let path = PathBuf::from(dir);
        if path.exists() {
            dialog = dialog.set_directory(path);
        }
    }

    dialog.blocking_pick_file().map(|path| path.to_string())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .setup(|app| {
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            }
            let _ = app.shell();
            let _ = app.dialog();
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![pick_inp_file])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
