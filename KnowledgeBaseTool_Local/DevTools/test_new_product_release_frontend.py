"""Frontend contract checks for the new-product release workspace."""

from html.parser import HTMLParser
from pathlib import Path
import unittest
import pytest


ROOT = Path(__file__).resolve().parents[1]
VIEWER = ROOT / "link_viewer"
APP_JS = VIEWER / "app_v8.js"

RELEASE_CONTROL_IDS = {
    "newProductReleaseView",
    "newProductReleaseWorkspace",
    "newProductReleaseWorkspaceList",
    "newProductReleaseStatus",
    "newProductReleaseBlockReason",
    "newProductReleaseTabState",
    "newProductReleaseReadOnly",
    "newProductReleaseEffectiveMethod",
    "newProductReleaseTriggerModel",
    "newProductReleasePublicKb",
    "newProductReleasePendingChain",
    "newProductReleaseIdempotent",
    "newProductReleasePreviewToken",
    "newProductReleaseConflictState",
    "newProductReleaseBatchId",
    "newProductReleaseDownstream",
    "newProductReleaseRefreshBtn",
    "newProductReleasePreviewBtn",
    "newProductReleasePublishBtn",
    "newProductReleaseCancelBtn",
    "newProductReleaseReapplyBtn",
    "newProductReleaseRetryOutboxBtn",
    "newProductReleaseReconcileBtn",
    "newProductReleaseConfirmImpact",
    "newProductReleaseConfirmFormal",
}


class IdCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []

    def handle_starttag(self, _tag, attrs):
        attributes = dict(attrs)
        if attributes.get("id"):
            self.ids.append(attributes["id"])


@pytest.mark.usefixtures("frontend_dist")
class NewProductReleaseFrontendTests(unittest.TestCase):
    def test_release_workspace_has_one_complete_control_set(self):
        for page_name in ("index.html", "dist/index.html"):
            with self.subTest(page=page_name):
                parser = IdCollector()
                parser.feed((VIEWER / page_name).read_text(encoding="utf-8"))
                counts = {control_id: parser.ids.count(control_id) for control_id in RELEASE_CONTROL_IDS}
                self.assertEqual(
                    {control_id: count for control_id, count in counts.items() if count != 1},
                    {},
                    f"{page_name} must contain exactly one complete release workspace",
                )

    def test_release_workspace_keeps_explicit_public_kb_confirmations(self):
        page = (VIEWER / "index.html").read_text(encoding="utf-8")
        self.assertIn('for="newProductReleaseConfirmImpact"', page)
        self.assertIn('for="newProductReleaseConfirmFormal"', page)
        self.assertIn("公共 KB 影响范围", page)
        self.assertIn("确认已核对正式发布内容", page)

    def test_publish_requires_a_fresh_preview_for_the_selected_model(self):
        script = APP_JS.read_text(encoding="utf-8")
        self.assertIn("function hasCurrentNewProductReleasePreview()", script)
        self.assertIn("context.previewModelId === context.modelId", script)
        self.assertIn("context.previewExpiresAt", script)
        self.assertIn("|| !hasCurrentNewProductReleasePreview()", script)
        self.assertIn("selectNewProductReleaseModel(modelId)", script)
        self.assertIn("if (!hasCurrentNewProductReleasePreview())", script)
        self.assertIn("请先对当前型号执行预览", script)

    def test_workspace_selects_a_pending_model_even_when_requests_exist(self):
        script = APP_JS.read_text(encoding="utf-8")
        self.assertIn("function getNewProductReleaseWorkspaceModelId(state, currentModelId)", script)
        self.assertIn("getNewProductReleaseWorkspaceModelId(state, window.newProductReleaseContext.modelId)", script)
        self.assertIn("item.status === 'pending_release'", script)
        self.assertNotIn("if (pendingModels.length && !pendingChain.length)", script)

    def test_formal_modification_details_show_the_release_model(self):
        script = APP_JS.read_text(encoding="utf-8")
        self.assertIn("function getModDetailsModelLabel(item = {})", script)
        self.assertIn("meta.model_id || meta.target_model", script)
        self.assertIn("${modelLabel}: ${modelId}", script)

    def test_new_kb_submission_marks_create_mode_without_baseline_snapshot(self):
        script = APP_JS.read_text(encoding="utf-8")
        self.assertIn("is_create: __kbEditIsCreateMode", script)
        self.assertIn("baseline_snapshot: __kbEditIsCreateMode ? null", script)

    def test_new_product_entry_loads_model_sources_on_first_open(self):
        script = APP_JS.read_text(encoding="utf-8")
        entry_branch = script.split("} else if (tabId === 'newProductEntryView') {", 1)[1].split("\n    }", 1)[0]
        self.assertIn("loadCopySources()", entry_branch)
        self.assertIn("sourceLoadSeq", script)

    def test_pending_modifications_show_snapshot_differences(self):
        script = APP_JS.read_text(encoding="utf-8")
        self.assertIn("record.before ?? record.before_json ?? record.baseline_snapshot", script)
        self.assertIn("record.after ?? record.after_json ?? record.pending_snapshot", script)
        self.assertIn("function pendingModificationDiff(record)", script)
        self.assertIn("pending-modification-diff-list", script)
        self.assertIn("target_model || record.product_name", script)


if __name__ == "__main__":
    unittest.main()
