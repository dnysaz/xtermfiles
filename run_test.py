from cli import FileExplorer
from textual.widgets import DirectoryTree
import sys

# Test that the tree can render local files
app = FileExplorer()

async def test_boot():
    async with app.run_test() as pilot:
        await pilot.pause()
        tree = app.query_one("#local-tree", DirectoryTree)
        print("Root node label:", getattr(tree.root, "label", "None"))
        print("Children count:", len(tree.root.children))
        print("Is expanded?", tree.root.is_expanded)
        
import asyncio
asyncio.run(test_boot())
