"""Direct tests of the hostile-tree file layer."""
import os
import stat

from helpers import Sandbox, make

from engine import safefs


class SafeFs(Sandbox):
    def setUp(self):
        super().setUp()
        self.root = make(self.docs / "proj")
        self.outside = self.home / ".zshrc"
        self.outside.write_text("SAFE\n", encoding="utf-8")

    def test_read_regular_file(self):
        (self.root / "a.txt").write_text("hello", encoding="utf-8")
        self.assertEqual(safefs.read_text(self.root, self.root / "a.txt"), "hello")

    def test_read_refuses_final_symlink(self):
        os.symlink(self.outside, self.root / "a.txt")
        self.assertIsNone(safefs.read_text(self.root, self.root / "a.txt"))

    def test_read_refuses_symlinked_folder_in_the_middle(self):
        os.symlink(self.home, self.root / "sub")
        self.assertIsNone(safefs.read_text(self.root, self.root / "sub" / ".zshrc"))

    def test_read_refuses_fifo_without_blocking(self):
        os.mkfifo(self.root / "fifo")
        self.assertIsNone(safefs.read_text(self.root, self.root / "fifo"))

    def test_read_size_cap_on_regular_file(self):
        (self.root / "big").write_bytes(b"a" * (safefs.MAX_READ + 1))
        self.assertIsNone(safefs.read_text(self.root, self.root / "big"))
        (self.root / "ok").write_bytes(b"a" * safefs.MAX_READ)
        self.assertEqual(len(safefs.read_text(self.root, self.root / "ok")), safefs.MAX_READ)

    def test_read_refuses_device(self):
        os.symlink("/dev/zero", self.root / "zero")
        self.assertIsNone(safefs.read_text(self.root, self.root / "zero"))

    def test_write_replaces_symlink_and_leaves_target(self):
        os.symlink(self.outside, self.root / "AGENTS.md")
        safefs.write_text(self.root, self.root / "AGENTS.md", "new")
        self.assertEqual(self.outside.read_text(), "SAFE\n")
        self.assertFalse(os.path.islink(self.root / "AGENTS.md"))
        self.assertEqual((self.root / "AGENTS.md").read_text(), "new")

    def test_write_refuses_symlinked_folder(self):
        os.symlink(self.home, self.root / ".harness")
        with self.assertRaises(safefs.Unsafe):
            safefs.write_text(self.root, self.root / ".harness" / "x.md", "x")
        self.assertFalse((self.home / "x.md").exists())

    def test_write_creates_parents_and_keeps_mode(self):
        safefs.write_text(self.root, self.root / "a" / "b" / "c.txt", "x")
        self.assertEqual((self.root / "a" / "b" / "c.txt").read_text(), "x")
        p = self.root / "plain"
        p.write_text("old")
        p.chmod(0o600)
        safefs.write_text(self.root, p, "new")
        self.assertEqual(stat.S_IMODE(p.stat().st_mode), 0o600)
        self.assertEqual([f for f in os.listdir(self.root) if f.endswith(".tmp")], [])

    def test_write_refuses_folder_in_the_way(self):
        (self.root / "d").mkdir()
        with self.assertRaises(safefs.Unsafe):
            safefs.write_text(self.root, self.root / "d", "x")

    def test_write_through_a_file_component_fails(self):
        (self.root / "f").write_text("x")
        with self.assertRaises((safefs.Unsafe, OSError)):
            safefs.write_text(self.root, self.root / "f" / "g.txt", "x")

    def test_paths_outside_root_refused(self):
        with self.assertRaises(safefs.Unsafe):
            safefs.write_text(self.root, self.root / ".." / "escape.txt", "x")
        with self.assertRaises(safefs.Unsafe):
            safefs.write_text(self.root, self.home / "escape.txt", "x")
        self.assertIsNone(safefs.read_text(self.root, self.home / ".zshrc"))

    def test_remove_symlink_not_target(self):
        os.symlink(self.outside, self.root / "link")
        self.assertTrue(safefs.remove(self.root, self.root / "link"))
        self.assertTrue(self.outside.exists())
        self.assertFalse(safefs.remove(self.root, self.root / "link"))

    def test_remove_refuses_folder(self):
        (self.root / "d").mkdir()
        with self.assertRaises(safefs.Unsafe):
            safefs.remove(self.root, self.root / "d")

    def test_exists_and_kind(self):
        os.symlink(self.outside, self.root / "link")
        (self.root / "d").mkdir()
        (self.root / "f").write_text("x")
        self.assertTrue(safefs.exists(self.root, self.root / "link"))
        self.assertFalse(safefs.is_regular(self.root, self.root / "link"))
        self.assertTrue(safefs.is_regular(self.root, self.root / "f"))
        self.assertTrue(safefs.is_dir(self.root, self.root / "d"))
        self.assertFalse(safefs.is_dir(self.root, self.root / "link"))
        self.assertFalse(safefs.exists(self.root, self.root / "missing"))

    def test_rmdir_only_empty_real_folders(self):
        (self.root / "e").mkdir()
        (self.root / "full").mkdir()
        (self.root / "full" / "x").write_text("x")
        self.assertTrue(safefs.rmdir(self.root, self.root / "e"))
        self.assertFalse(safefs.rmdir(self.root, self.root / "full"))
        os.symlink(self.home, self.root / "ln")
        self.assertFalse(safefs.rmdir(self.root, self.root / "ln"))
        self.assertTrue(self.home.exists())

    def test_inside_rejects_symlink_component(self):
        os.symlink(self.home, self.root / "sub")
        with self.assertRaises(safefs.Unsafe):
            safefs.inside(self.root, self.root / "sub" / "x")
        self.assertEqual(safefs.inside(self.root, self.root / "new" / "x"), self.root / "new" / "x")
