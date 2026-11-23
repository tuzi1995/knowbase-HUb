import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import test from 'node:test';

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright');
const source = readFileSync(new URL('./app_v8.js', import.meta.url), 'utf8');
const html = readFileSync(new URL('./index.html', import.meta.url), 'utf8');
const slice = (start, end) => {
    const offset = source.indexOf(start);
    assert.ok(offset >= 0, start);
    const limit = source.indexOf(end, offset);
    assert.ok(limit > offset, end);
    return source.slice(offset, limit);
};

test('similar-question picker filters entries without changing draft order', async () => {
    const browser = await chromium.launch({
        headless: true,
        ...(process.env.PLAYWRIGHT_EXECUTABLE_PATH ? { executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH } : {}),
    });
    try {
        const page = await browser.newPage();
        const modalStart = html.indexOf('<!-- KB Similar Question Picker Modal -->');
        const modalEnd = html.indexOf('<!-- AI Answer Requirement Modal -->', modalStart);
        assert.ok(modalStart >= 0 && modalEnd > modalStart);
        await page.setContent(`<form id="kbEditForm"><textarea name="similar_questions"></textarea></form>${html.slice(modalStart, modalEnd)}`);
        await page.addScriptTag({ content: `
            let __kbSimilarPickerItems = null;
            const parseSmartListValue = value => String(value ?? '').split(/[\\n,，]/).map(item => item.trim()).filter(Boolean);
            ${slice('function openKBSimilarQuestionPicker()', 'let __kbEditTagsLoadState =')}
        ` });

        await page.evaluate(() => {
            document.querySelector('[name="similar_questions"]').value = [
                ...Array.from({ length: 113 }, (_, index) => `普通问题 ${index + 1}`),
                '设备出现损坏怎么办',
                '维修地点在哪里',
            ].join('\n');
            openKBSimilarQuestionPicker();
        });
        const search = page.locator('#kbSimilarPickerSearch');
        assert.equal(await page.locator('.kb-similar-picker-row').count(), 115);
        assert.equal(await page.locator('#kbSimilarPickerCount').textContent(), '115 条相似问');

        await search.fill('维修');
        assert.equal(await page.locator('.kb-similar-picker-row:visible').count(), 1);
        assert.equal(await page.locator('#kbSimilarPickerCount').textContent(), '匹配 1 / 共 115 条');
        assert.equal(await page.locator('.kb-similar-picker-index:visible').textContent(), '115');
        await page.locator('.kb-similar-picker-row:visible textarea').fill('维修点怎么找');
        assert.equal(await page.locator('#kbSimilarPickerCount').textContent(), '匹配 1 / 共 115 条');

        await page.locator('#kbSimilarPickerClear').click();
        assert.equal(await search.inputValue(), '');
        assert.equal(await page.locator('.kb-similar-picker-row:visible').count(), 115);
        await search.fill('没有此问题');
        assert.equal(await page.locator('#kbSimilarPickerCount').textContent(), '匹配 0 / 共 115 条');
        assert.equal(await page.locator('#kbSimilarPickerEmpty').textContent(), '没有匹配的相似问，试试其他关键词或清空搜索');
        await page.locator('#kbSimilarPickerClear').click();
        await page.locator('.kb-similar-picker-remove').nth(0).click();
        assert.equal(await page.locator('#kbSimilarPickerCount').textContent(), '114 条相似问');
        assert.equal(await page.locator('.kb-similar-picker-row').nth(0).locator('textarea').inputValue(), '普通问题 2');
        await browser.close();
    } catch (error) {
        await browser.close();
        throw error;
    }
});
