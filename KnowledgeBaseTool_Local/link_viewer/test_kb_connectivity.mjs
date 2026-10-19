import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const source = readFileSync(new URL('./app_v8.js', import.meta.url), 'utf8');
function slice(start, end) {
    const offset = source.indexOf(start);
    assert.ok(offset >= 0, start);
    const limit = source.indexOf(end, offset);
    assert.ok(limit > offset, end);
    return source.slice(offset, limit);
}

function setup({ reachable = true, status = 200, online = false } = {}) {
    const state = { requests: [], toasts: [], alerts: [], saved: 0, drafts: 0, logins: 0 };
    const storage = new Map();
    const button = {};
    const context = vm.createContext({
        console: { log() {}, error() {} },
        navigator: { onLine: online },
        window: { location: { href: 'http://127.0.0.1:8085/?embed=1' }, addEventListener() {} },
        URL, AbortController, setTimeout, clearTimeout,
        fetch: async (url, opts) => {
            state.requests.push({ url: String(url), ...opts });
            if (!reachable) throw new TypeError('Failed to fetch');
            return { status, text: async () => JSON.stringify(status === 200
                ? { success: true, question_wiki_id: 'diagnostic-only', candidates: [] }
                : { success: false, message: 'Server error' }) };
        },
        API_BASE: '/api',
        localStorage: { getItem: key => storage.get(key), setItem: (key, value) => storage.set(key, value) },
        KB_EDIT_PENDING_SYNC_KEY: 'pending-test',
        document: { getElementById: () => button },
        __kbEditSyncingPending: false,
        __kbEditBuildSubmitPayload: () => ({ data: { question_wiki_id: 'diagnostic-only' }, tagNames: [] }),
        __kbEditBuildSavedDiffs: () => [],
        __kbEditBuildReleaseSubmission: async () => null,
        __kbEditSaveDraftNow: () => state.drafts++,
        __kbEditSetDraftStatus: value => { state.draftStatus = value; },
        __kbEditInitialDigest: {},
        __kbParseTagNames: () => [],
        postKbEditEmbedMessage() {},
        __kbEditCollectDigest: () => ({ question: '足够四个字的问题', answer: '' }),
        __kbEditClearDraft() {},
        closeKBEditModal: () => state.saved++,
        clearKBCache() {}, loadKBTable: async () => {}, kbCurrentPage: 1,
        knowledgeGraphState: { editingWikiId: '' },
        __kbEditQualityContext: null, __kbEditWorkflowContext: null,
        __kbEditDraftContextId: 'diagnostic-only', kbEditEmbedRequest: null,
        showToast: message => state.toasts.push(message),
        alert: message => state.alerts.push(message),
        showLogin: () => state.logins++,
        openFeedbackModal() {},
        __kbEditIsCreateMode: true, __kbEditReferenceTimer: null, __kbEditReferenceRequestSeq: 0,
        __kbEditConfirmedReferences: [],
        __kbEditSetReferenceStatus: message => { state.referenceStatus = message; },
        __kbEditRenderReferenceCandidates() {},
    });
    vm.runInContext(slice('async function api(', 'window.newProductReleaseContext ='), context);
    const helperStart = source.indexOf('async function __kbEditCanReachServer(');
    if (helperStart >= 0) {
        vm.runInContext(source.slice(helperStart, source.indexOf('function __kbEditLoadPendingSyncQueue(', helperStart)), context);
    }
    vm.runInContext(slice('function __kbEditLoadPendingSyncQueue(', 'function __kbEditRefreshDirtyState('), context);
    vm.runInContext(slice('async function saveKBItem() {', '// Export Logic'), context);
    vm.runInContext(slice('async function kbRefreshReferenceCandidates(', 'function kbToggleReferenceCandidate('), context);
    return { context, state, button };
}

test('browser offline flag does not block saving to a reachable local service', async () => {
    const { context, state, button } = setup();
    await context.saveKBItem();
    assert.equal(state.saved, 1);
    assert.equal(context.__kbEditLoadPendingSyncQueue().length, 0);
    assert.ok(state.requests.some(request => request.url === '/api/kb/update'));
    assert.equal(button.disabled, false);
    assert.equal(state.requests[0].method, 'HEAD');
    assert.equal(state.requests[0].cache, 'no-store');
    assert.equal(new URL(state.requests[0].url).origin, 'http://127.0.0.1:8085');
});

test('unreachable service preserves content and tags as a pending local draft', async () => {
    const { context, state } = setup({ reachable: false });
    await context.saveKBItem();
    assert.equal(state.saved, 0);
    assert.equal(state.drafts, 1);
    assert.equal(state.draftStatus, 'pending_sync');
    assert.equal(context.__kbEditLoadPendingSyncQueue().length, 1);
    assert.match(state.toasts[0], /无法连接.*服务/);
    assert.equal(state.requests.some(request => request.method === 'POST'), false);
});

test('HTTP failures keep the real server error and do not masquerade as offline', async () => {
    const { context, state } = setup({ status: 500 });
    await context.saveKBItem();
    assert.match(state.alerts[0], /Server error/);
    assert.equal(context.__kbEditLoadPendingSyncQueue().length, 0);
});

test('expired login still requests authentication instead of queuing an offline write', async () => {
    const { context, state } = setup({ status: 401 });
    await context.saveKBItem();
    assert.equal(state.logins, 1);
    assert.match(state.alerts[0], /Unauthorized/);
    assert.equal(context.__kbEditLoadPendingSyncQueue().length, 0);
});

test('existing pending content and tags sync even when browser still reports offline', async () => {
    const { context, state } = setup();
    context.__kbEditQueuePendingSync({ data: { question_wiki_id: 'diagnostic-only' }, tagNames: ['标签'] });
    await context.__kbEditSyncPendingQueue();
    assert.equal(context.__kbEditLoadPendingSyncQueue().length, 0);
    assert.ok(state.requests.some(request => request.url === '/api/kb/item/tags'));
    assert.match(state.toasts[0], /已自动同步/);
});

test('unreachable service preserves existing queue for the next attempt', async () => {
    const { context, state } = setup({ reachable: false });
    context.__kbEditQueuePendingSync({ data: { question_wiki_id: 'diagnostic-only' }, tagNames: [] });
    await context.__kbEditSyncPendingQueue();
    assert.equal(context.__kbEditLoadPendingSyncQueue().length, 1);
    assert.equal(context.__kbEditSyncingPending, false);
    assert.equal(state.toasts.length, 0);
});

test('simultaneous retries do not submit the pending write twice during reachability check', async () => {
    const { context, state } = setup();
    context.__kbEditQueuePendingSync({ data: { question_wiki_id: 'diagnostic-only' }, tagNames: [] });
    await Promise.all([context.__kbEditSyncPendingQueue(), context.__kbEditSyncPendingQueue()]);
    assert.equal(state.requests.filter(request => request.url === '/api/kb/update').length, 1);
});

test('reference candidates can load from the local service while browser reports offline', async () => {
    const { context, state } = setup();
    await context.kbRefreshReferenceCandidates();
    assert.ok(state.requests.some(request => request.url === '/api/kb/reference-candidates'));
    assert.match(state.referenceStatus, /未找到可推荐知识/);
});

test('normal online saves do not add a reachability request', async () => {
    const { context, state } = setup({ online: true });
    await context.saveKBItem();
    assert.equal(state.saved, 1);
    assert.equal(state.requests.length, 1);
    assert.equal(state.requests[0].url, '/api/kb/update');
});

test('a stalled reachability check times out and restores the save button with a local draft', async () => {
    const { context, state, button } = setup();
    let timeoutCallback;
    let timeoutCleared = false;
    context.setTimeout = (callback, milliseconds) => {
        assert.equal(milliseconds, 4000);
        timeoutCallback = callback;
        return 1;
    };
    context.clearTimeout = () => { timeoutCleared = true; };
    context.fetch = async (_url, options) => new Promise((_resolve, reject) => {
        options.signal.addEventListener('abort', () => reject(new Error('aborted')));
        timeoutCallback();
    });
    await context.saveKBItem();
    assert.equal(state.drafts, 1);
    assert.equal(context.__kbEditLoadPendingSyncQueue().length, 1);
    assert.equal(button.disabled, false);
    assert.equal(timeoutCleared, true);
});
