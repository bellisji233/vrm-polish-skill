// Model files stay in this browser/origin. Nothing is uploaded.
const DB_NAME = 'vrm-live-studio';
let pendingDB;
function database() {
  if (!pendingDB) pendingDB = new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => {
      const db = req.result;
      db.createObjectStore('models', { keyPath: 'id' });
      db.createObjectStore('preferences', { keyPath: 'key' });
    };
    req.onsuccess = () => {
      req.result.onversionchange = () => { req.result.close(); pendingDB = null; };
      resolve(req.result);
    };
    req.onerror = () => { pendingDB = null; reject(req.error); };
    req.onblocked = () => { pendingDB = null; reject(new Error('请关闭其他旧版预览页后重试')); };
  });
  return pendingDB;
}
async function transaction(stores, mode, callback) {
  const db = await database();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(stores, mode);
    let result;
    tx.oncomplete = () => resolve(result);
    tx.onabort = () => reject(tx.error || new Error('模型保存被中断'));
    tx.onerror = () => reject(tx.error || new Error('无法访问浏览器模型库'));
    try { callback(tx, value => { result = value; }); }
    catch (e) { tx.abort(); reject(e); }
  });
}
export function listModels() {
  return transaction(['models'], 'readonly', (tx, done) => {
    const rows = []; const req = tx.objectStore('models').openCursor();
    req.onsuccess = () => {
      const cursor = req.result;
      if (!cursor) { done(rows.sort((a,b) => b.savedAt - a.savedAt)); return; }
      const { id, name, size, savedAt } = cursor.value;
      rows.push({ id, name, size, savedAt }); cursor.continue();
    };
  });
}
export function saveModel(file) {
  const id = JSON.stringify([file.name, file.size, file.lastModified]);
  return transaction(['models', 'preferences'], 'readwrite', (tx, done) => {
    tx.objectStore('models').put({ id, name:file.name, size:file.size, savedAt:Date.now(), blob:file });
    tx.objectStore('preferences').put({ key:'lastModel', value:id }); done(id);
  });
}
export function getModel(id) {
  return transaction(['models'], 'readonly', (tx, done) => {
    const req = tx.objectStore('models').get(id); req.onsuccess = () => done(req.result);
  });
}
export function getLastModel() {
  return transaction(['preferences'], 'readonly', (tx, done) => {
    const req = tx.objectStore('preferences').get('lastModel'); req.onsuccess = () => done(req.result?.value);
  });
}
export function selectModel(id) {
  return transaction(['preferences'], 'readwrite', tx => {
    tx.objectStore('preferences').put({ key:'lastModel', value:id });
  });
}
export function deleteModel(id) {
  return transaction(['models', 'preferences'], 'readwrite', tx => {
    tx.objectStore('models').delete(id);
    const prefs = tx.objectStore('preferences'); const req = prefs.get('lastModel');
    req.onsuccess = () => { if (req.result?.value === id) prefs.delete('lastModel'); };
  });
}
