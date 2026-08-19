import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const source = readFileSync(new URL('./app_v8.js', import.meta.url), 'utf8');
const handlerSource = source.match(/function smToggleCellExpand\(key, e\) \{[\s\S]*?\n\}\n\nfunction smToggleOtherInfo/)?.[0]
    .replace(/\n\nfunction smToggleOtherInfo$/, '');

assert.ok(handlerSource, 'smToggleCellExpand source should be present');

function createFixture() {
    const expandedKeys = new Set();
    const classes = new Set(['sm-cell', 'is-overflow']);
    const attributes = new Map();
    const content = {
        tagName: 'TEXTAREA',
        style: { height: '' },
        scrollHeight: 680,
        clientHeight: 72
    };
    const cell = {
        classList: {
            toggle(name, force) {
                if (force) classes.add(name);
                else classes.delete(name);
            }
        },
        getAttribute(name) {
            return name === 'data-cell-key' ? '46:faq_answer' : null;
        },
        querySelector() {
            return content;
        }
    };
    const button = {
        textContent: '展开▼',
        closest() {
            return cell;
        },
        setAttribute(name, value) {
            attributes.set(name, value);
        }
    };
    const eventCounts = { prevented: 0, stopped: 0 };
    const event = {
        currentTarget: button,
        preventDefault() {
            eventCounts.prevented += 1;
        },
        stopPropagation() {
            eventCounts.stopped += 1;
        }
    };
    const handler = new Function('smWorkbenchExpanded', `${handlerSource}; return smToggleCellExpand;`)(expandedKeys);
    return { attributes, button, cell, classes, content, event, eventCounts, expandedKeys, handler };
}

test('smart mapping expands and collapses one cell without rebuilding the table', () => {
    const fixture = createFixture();

    fixture.handler('46:faq_answer', fixture.event);
    assert.equal(fixture.expandedKeys.has('46:faq_answer'), true);
    assert.equal(fixture.classes.has('is-expanded'), true);
    assert.equal(fixture.button.textContent, '收起▲');
    assert.equal(fixture.attributes.get('aria-expanded'), 'true');
    assert.equal(fixture.content.style.height, '520px');

    fixture.content.clientHeight = 72;
    fixture.handler('46:faq_answer', fixture.event);
    assert.equal(fixture.expandedKeys.has('46:faq_answer'), false);
    assert.equal(fixture.classes.has('is-expanded'), false);
    assert.equal(fixture.button.textContent, '展开▼');
    assert.equal(fixture.attributes.get('aria-expanded'), 'false');
    assert.equal(fixture.content.style.height, '');
    assert.equal(fixture.eventCounts.prevented, 2);
    assert.equal(fixture.eventCounts.stopped, 2);
});
