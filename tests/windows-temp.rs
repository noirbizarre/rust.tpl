#[test]
fn rust_temporary_storage_resolves_to_the_dev_drive() {
    let expected = std::path::PathBuf::from(std::env::var_os("DEV_DRIVE").unwrap())
        .join("test-temp")
        .canonicalize()
        .unwrap();
    // A shell-only check could pass while Rust still resolves its temporary directory on NTFS.
    assert_eq!(std::env::temp_dir().canonicalize().unwrap(), expected);
}
