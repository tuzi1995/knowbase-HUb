import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import test from 'node:test';

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright');
const source = readFileSync(new URL('./app_v8.js', import.meta.url), 'utf8');
const html = readFileSync(new URL('./index.html', import.meta.url), 'utf8')
    .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, '');
const slice = (start, end) => {
    const offset = source.indexOf(start);
    assert.ok(offset >= 0, start);
    const limit = source.indexOf(end, offset);
    assert.ok(limit > offset, end);
    return source.slice(offset, limit);
};

test('editor tag dropdown preserves manual tags and integrates with dirty state and submit payload', async () => {
    const browser = await chromium.launch({
        headless: true,
        ...(process.env.PLAYWRIGHT_EXECUTABLE_PATH ? { executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH } : {}),
    });
    try {
        const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
        const origin = process.env.KB_TEST_ORIGIN || 'http://127.0.0.1:8085';
        let fail = false;
        const tags = ['故障', '维护', 'FAQ', '<特别标签>', '充电-电量15%', '充电-电量20%', '导购-产品对比', '服务-延保购买', '会员中心', '很长的标签'.repeat(16)];
        // Use the real markup and CSS, with isolated tag data and no production writes.
        await page.route(`${origin}/**`, async route => {
            const url = new URL(route.request().url());
            if (url.pathname === '/') return route.fulfill({ contentType: 'text/html', body: html });
            if (url.pathname === '/api/kb/tags') return route.fulfill({
                status: fail ? 500 : 200, contentType: 'application/json',
                body: JSON.stringify(fail ? { message: 'failed' } : tags),
            });
            if (url.pathname.startsWith('/api/')) throw new Error(`Unexpected API call: ${url.pathname}`);
            return route.continue();
        });
        await page.goto(origin, { waitUntil: 'networkidle' });
        await page.addScriptTag({ content: `
            let kbAllTags = [], kbTagsLoadPromise = null;
            let __kbEditIsCreateMode = false, __kbEditTouched = false, __kbEditInitialDigest = null;
            let __kbEditTemplateRefId = '', __kbEditConfirmedReferences = [], __kbEditBaseVersion = 1;
            let __kbEditWorkflowContext = null, __kbEditQualityContext = null;
            let kbEditEmbedRequest = null, kbActionEmbedRequest = null;
            const __kbEditNormalizeText = v => String(v ?? '').trim();
            const parseSmartListValue = v => String(v ?? '').split(/[,，\\n]/).map(s => s.trim()).filter(Boolean);
            const __kbEditResolveProductNames = v => ({ values: parseSmartListValue(v) });
            const __kbEditRenderPreview = () => __kbEditRenderTagChips();
            const __kbEditSetDraftStatus = () => {};
            const __kbEditScheduleDraftSave = () => {};
            const __kbEditSyncLinkTypeValue = () => {};
            const __kbEditSetLinkTypeValue = () => {};
            const __kbEditSyncTemplateReferenceUi = () => {};
            const __kbEditRenderReferenceCandidates = () => {};
            const __kbEditApplyProductsToForm = () => {};
            async function api(path) {
                const response = await fetch('/api' + path);
                if (!response.ok) throw new Error('Tag request failed');
                return response.json();
            }
            ${slice('function normalizeKnowledgeBaseTags(', 'async function fetchKBAllTags()')}
            ${slice('let __kbEditTagsLoadState =', 'async function __kbEditRefreshReleaseOptionsVisibility()')}
            ${slice('function __kbEditCollectDigest()', 'const KB_EDIT_EMBED_LOG_FIELDS =')}
            ${slice('function __kbEditRefreshDirtyState()', 'function __kbEditFormatListTextarea(')}
            ${slice('function __kbEditBuildSubmitPayload()', 'function __kbEditHandleConflict(')}
            ${slice('function __kbEditRestoreDraftDigest(', 'function __kbEditHasUnsavedChanges(')}
        ` });
        await page.evaluate(() => {
            const modal = document.getElementById('kbEditModal');
            modal.classList.add('is-open');
            modal.style.display = 'flex';
            const input = document.getElementById('kbEditTagsInput');
            input.value = '维护, 手动新标签';
            input.closest('details').open = true;
            window.submits = 0;
            document.getElementById('kbEditForm').addEventListener('submit', event => {
                event.preventDefault(); window.submits++;
            });
            __kbEditBindTagsSelector();
            __kbEditBindDirtyChecker();
            __kbEditCaptureInitialState(false);
        });
        const input = page.locator('#kbEditTagsInput');
        const button = page.locator('#kbEditTagsDropdownBtn');
        const search = page.locator('#kbEditTagsSearch');
        const checkbox = tag => page.locator('.kb-edit-tag-option').filter({ hasText: tag }).locator('input');
        const chip = tag => page.locator('.kb-edit-tag-chip').filter({ hasText: tag });
        const names = () => page.evaluate(() => __kbEditGetTagNames());
        assert.equal(await button.getAttribute('aria-expanded'), 'false');
        assert.equal(await page.locator('#kbEditTagsCount').textContent(), '已选 2');
        assert.equal(await page.locator('.kb-edit-tag-chip').count(), 2);
        assert.equal(await page.locator('#saveKBItemBtn').isDisabled(), true);
        await button.click();
        await checkbox('维护').waitFor();
        assert.equal(await checkbox('维护').isChecked(), true);
        await checkbox('故障').check();
        assert.equal(await input.inputValue(), '维护, 手动新标签, 故障');
        assert.equal(await page.locator('#saveKBItemBtn').isEnabled(), true);
        assert.deepEqual(await page.evaluate(() => __kbEditBuildSubmitPayload().tagNames), ['维护', '手动新标签', '故障']);
        assert.ok((await page.evaluate(() => __kbEditBuildSubmitPayload().data.changed_fields)).includes('kb_tags_input'));
        await checkbox('故障').uncheck();
        assert.equal(await page.locator('#saveKBItemBtn').isDisabled(), true);
        await checkbox('维护').uncheck();
        assert.equal(await input.inputValue(), '手动新标签');
        await search.fill('faq');
        assert.equal(await page.locator('.kb-edit-tag-option').count(), 1);
        await checkbox('FAQ').check();
        assert.equal(await search.inputValue(), '');
        await search.fill('故障，另一个新标签,');
        assert.deepEqual(await names(), ['手动新标签', 'FAQ', '故障', '另一个新标签']);
        assert.equal(await checkbox('FAQ').isChecked(), true);
        await checkbox('FAQ').uncheck();
        assert.equal(await input.inputValue(), '手动新标签, 故障, 另一个新标签');
        await search.fill('新建标签');
        await page.getByRole('button', { name: '创建新标签“新建标签”', exact: true }).click();
        assert.ok((await names()).includes('新建标签'));
        await search.fill('新建标签');
        await search.press('Enter');
        assert.equal(await chip('新建标签').count(), 1);
        assert.ok((await chip('新建标签').getAttribute('class')).includes('is-duplicate'));
        await search.press('Backspace');
        assert.equal(await chip('新建标签').count(), 0);
        await page.getByRole('button', { name: '删除标签 故障', exact: true }).click();
        assert.equal(await checkbox('故障').isChecked(), false);
        await search.fill('不存在');
        await page.getByRole('button', { name: '创建新标签“不存在”', exact: true }).waitFor();
        await search.press('Enter');
        assert.equal(await page.evaluate(() => submits), 0);
        assert.ok((await names()).includes('不存在'));
        await search.press('Escape');
        assert.equal(await button.getAttribute('aria-expanded'), 'false');
        assert.equal(await search.evaluate(element => element === document.activeElement), false);
        await button.click();
        await search.fill('');
        await checkbox('<特别标签>').waitFor();
        assert.equal(await page.locator('#kbEditTagsOptions img').count(), 0);
        await page.locator('#kbEditTitle').click();
        assert.equal(await button.getAttribute('aria-expanded'), 'false');
        fail = true;
        await button.click();
        await page.getByRole('button', { name: '重新加载', exact: true }).waitFor();
        assert.deepEqual(await names(), ['手动新标签', '另一个新标签', '不存在']);
        fail = false;
        tags.push('刚保存的新标签');
        await page.getByRole('button', { name: '重新加载', exact: true }).click();
        await checkbox('刚保存的新标签').waitFor();
        await page.evaluate(() => {
            document.getElementById('kbEditTagsInput').value = 'FAQ';
            __kbEditBindTagsSelector();
        });
        await button.click();
        await checkbox('FAQ').waitFor();
        assert.equal(await checkbox('FAQ').isChecked(), true);
        assert.equal(await search.inputValue(), '');
        assert.equal(await page.locator('.kb-edit-tag-chip').count(), 1);
        await search.fill('草稿中的新标签');
        await page.evaluate(() => {
            const digest = __kbEditCollectDigest();
            __kbEditSetTagNames([]);
            __kbEditRestoreDraftDigest(digest);
        });
        assert.deepEqual(await names(), ['FAQ', '草稿中的新标签']);
        assert.equal(await chip('草稿中的新标签').count(), 1);
        assert.equal(await search.inputValue(), '');
        await page.getByRole('button', { name: '删除标签 草稿中的新标签', exact: true }).click();
        await search.fill('未按回车');
        assert.deepEqual(await page.evaluate(() => __kbEditBuildSubmitPayload().tagNames), ['FAQ', '未按回车']);
        assert.equal(await search.inputValue(), '');
        await page.locator('#kbEditTagsClear').click();
        assert.deepEqual(await names(), []);
        assert.equal(await page.locator('#kbEditTagsCount').textContent(), '已选 0');
        assert.equal(await page.locator('#kbEditTagsClear').isHidden(), true);
        await search.fill('充电-电量15%,导购-产品对比,服务-延保购买,会员中心,');
        const colors = await page.locator('.kb-edit-tag-chip').evaluateAll(elements => elements.map(element => getComputedStyle(element).color));
        assert.equal(new Set(colors).size, 4);
        for (const width of [1600, 390]) {
            await page.setViewportSize({ width, height: 1000 });
            await page.locator('#kbEditTagsDropdown').scrollIntoViewIfNeeded();
            const layout = await page.locator('#kbEditTagsSelector').evaluate(element => {
                const rect = element.getBoundingClientRect();
                return { left: rect.left, right: rect.right, scroll: element.scrollWidth, client: element.clientWidth };
            });
            assert.ok(layout.left >= 0 && layout.right <= width, JSON.stringify(layout));
            assert.ok(layout.scroll <= layout.client + 1, JSON.stringify(layout));
            assert.ok(await page.locator('#kbEditTagsOptions').evaluate(element => element.clientHeight <= 220));
            await page.screenshot({ path: `/tmp/knowbase-edit-tags-refined-${width}.png` });
        }
        await checkbox('很长的标签').check();
        const overflow = await page.locator('#kbEditTagsSelector').evaluate(element => element.scrollWidth - element.clientWidth);
        assert.ok(overflow <= 1);
        await search.fill('服务');
        await search.evaluate(element => element.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', isComposing: true, bubbles: true })));
        assert.equal(await search.inputValue(), '服务');
        await search.fill('');
        await page.locator('#kbEditTagsClear').click();
        tags.splice(0);
        await button.click();
        await button.click();
        await page.getByText('暂无已有标签', { exact: true }).waitFor();
        await search.fill('没有已有标签时也能手动新增');
        assert.deepEqual(await page.evaluate(() => __kbEditBuildSubmitPayload().tagNames), ['没有已有标签时也能手动新增']);
        // Chinese composition must not turn punctuation into a tag before composition ends.
        await page.evaluate(() => {
            __kbEditSetTagNames([]);
            const input = document.getElementById('kbEditTagsSearch');
            input.value = '输入中，';
            input.dispatchEvent(new InputEvent('input', { bubbles: true, isComposing: true }));
        });
        assert.deepEqual(await names(), []);
        await page.evaluate(() => document.getElementById('kbEditTagsSearch').dispatchEvent(new CompositionEvent('compositionend', { bubbles: true })));
        assert.deepEqual(await names(), ['输入中']);
    } finally {
        await browser.close();
    }
});
