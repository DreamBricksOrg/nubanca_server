(function () {
  "use strict";

  const PHOTO_DURATION_MS = 210000;

  function openDatabase() {
    return new Promise((resolve, reject) => {
      if (typeof indexedDB === "undefined" || !indexedDB) {
        reject(new Error("Histórico local indisponível neste navegador."));
        return;
      }
      let settled = false;
      const fail = () => {
        settled = true;
        clearTimeout(timer);
        reject(new Error("Não foi possível abrir o histórico local."));
      };
      const timer = setTimeout(fail, 4000);
      let request;
      try {
        request = indexedDB.open("nubanca-print-history", 2);
      } catch (error) {
        clearTimeout(timer);
        reject(error);
        return;
      }
      request.onupgradeneeded = () => {
        const db = request.result;
        if (!db.objectStoreNames.contains("photos")) {
          const photos = db.createObjectStore("photos", { keyPath: ["scope", "key"] });
          photos.createIndex("scope", "scope");
        }
        if (!db.objectStoreNames.contains("queues")) db.createObjectStore("queues", { keyPath: "scope" });
        const jobs = db.createObjectStore("jobs", { keyPath: "id", autoIncrement: true });
        jobs.createIndex("dispatch", ["scope", "queuedAt", "id"]);
        const photos = request.transaction.objectStore("photos");
        const queues = request.transaction.objectStore("queues");
        // V1 retained only each photo's last dispatch. Keep its count and forecast
        // as an opaque floor; missing older dispatches cannot be reconstructed.
        const reconcileAnchors = () => {
          let scope;
          let tail = 0;
          const ordered = jobs.index("dispatch").openCursor();
          ordered.onsuccess = () => {
            const cursor = ordered.result;
            if (!cursor) return;
            const job = cursor.value;
            if (scope !== job.scope) { scope = job.scope; tail = 0; }
            tail = Math.max(Math.max(job.queuedAt, tail) + PHOTO_DURATION_MS, job.legacyReadyAt);
            cursor.update({ ...job, readyAt: tail });
            const photo = photos.get([scope, job.key]);
            photo.onsuccess = () => {
              photos.put({ ...photo.result, readyAt: tail });
              const queue = queues.get(scope);
              queue.onsuccess = () => {
                queues.put({ scope, readyAt: Math.max(queue.result?.readyAt || 0, tail), lastQueuedAt: job.queuedAt });
                cursor.continue();
              };
            };
          };
        };
        const existing = photos.openCursor();
        existing.onsuccess = () => {
          const cursor = existing.result;
          if (!cursor) { reconcileAnchors(); return; }
          const row = cursor.value;
          const anchor = jobs.add({
            scope: row.scope, key: row.key, queuedAt: row.queuedAt,
            readyAt: row.readyAt, legacyReadyAt: row.readyAt,
          });
          anchor.onsuccess = () => {
            cursor.update({ ...row, latestJobId: anchor.result });
            cursor.continue();
          };
        };
      };
      request.onerror = fail;
      request.onblocked = fail;
      request.onsuccess = () => {
        clearTimeout(timer);
        const db = request.result;
        if (settled) {
          db.close();
          return;
        }
        settled = true;
        db.onversionchange = () => db.close();
        resolve(db);
      };
    });
  }

  async function transact(stores, mode, run) {
    const db = await openDatabase();
    return new Promise((resolve, reject) => {
      let result;
      const tx = db.transaction(stores, mode);
      tx.oncomplete = () => { db.close(); resolve(result); };
      tx.onabort = () => {
        db.close();
        reject(tx.error || new Error("Não foi possível salvar o histórico local."));
      };
      try {
        run(tx, (value) => { result = value; });
      } catch (error) {
        tx.abort();
        db.close();
        reject(error);
      }
    });
  }

  function record(scope, key, queuedAt) {
    const timestamp = Date.parse(queuedAt);
    if (!scope || typeof key !== "string" || !key || !Number.isFinite(timestamp)) {
      return Promise.reject(new Error("Dados de impressão inválidos para o histórico."));
    }
    // Jobs, photo summaries and the queue tail commit together across tabs.
    return transact(["photos", "queues", "jobs"], "readwrite", (tx, finish) => {
      const photos = tx.objectStore("photos");
      const queues = tx.objectStore("queues");
      const jobs = tx.objectStore("jobs");
      const dispatch = jobs.index("dispatch");
      const queue = queues.get(scope);
      const done = () => {
        const current = photos.get([scope, key]);
        current.onsuccess = () => finish(current.result);
      };
      queue.onsuccess = () => {
        const previous = photos.get([scope, key]);
        previous.onsuccess = () => {
          const job = { scope, key, queuedAt: timestamp };
          const added = jobs.add(job);
          added.onsuccess = () => {
            job.id = added.result;
            // Equal timestamps are distinct dispatches, ordered by transaction ID.
            const newest = !previous.result || timestamp >= previous.result.queuedAt;
            const row = newest ? {
              scope, key, filename: key.split("/").pop(), queuedAt: timestamp,
              latestJobId: job.id,
            } : previous.result;
            row.printCount = (previous.result?.printCount || 0) + 1;
            const saveJob = (tail) => {
              job.readyAt = Math.max(timestamp, tail) + PHOTO_DURATION_MS;
              jobs.put(job);
              if (newest) row.readyAt = job.readyAt;
              photos.put(row);
            };
            // Normal chronological arrivals touch only this job and its summary.
            if (!queue.result || timestamp >= queue.result.lastQueuedAt) {
              saveJob(queue.result?.readyAt || 0);
              queues.put({ scope, readyAt: job.readyAt, lastQueuedAt: timestamp });
              done();
              return;
            }
            const position = [scope, timestamp, job.id];
            const predecessor = dispatch.openCursor(IDBKeyRange.bound([scope], position, false, true), "prev");
            predecessor.onsuccess = () => {
              saveJob(predecessor.result?.value.readyAt || 0);
              let tail = job.readyAt;
              // Read only the delayed job's suffix, stopping at an unchanged
              // forecast (usually an idle gap). No full-history array rewrite.
              const suffix = dispatch.openCursor(IDBKeyRange.bound(position, [scope, []], true, true));
              suffix.onsuccess = () => {
                const cursor = suffix.result;
                if (!cursor) {
                  queues.put({ ...queue.result, scope, readyAt: tail });
                  done();
                  return;
                }
                const later = cursor.value;
                const readyAt = Math.max(
                  Math.max(later.queuedAt, tail) + PHOTO_DURATION_MS,
                  later.legacyReadyAt || 0,
                );
                if (readyAt === later.readyAt) { done(); return; }
                tail = readyAt;
                cursor.update({ ...later, readyAt });
                const summary = photos.get([scope, later.key]);
                summary.onsuccess = () => {
                  if (summary.result?.latestJobId === later.id) {
                    photos.put({ ...summary.result, readyAt });
                  }
                  cursor.continue();
                };
              };
            };
          };
        };
      };
    });
  }

  function list(scope) {
    return transact(["photos"], "readonly", (tx, finish) => {
      const request = tx.objectStore("photos").index("scope").getAll(scope);
      request.onsuccess = () => finish(request.result);
    });
  }

  function estimate(scope, key, now = Date.now()) {
    return transact(["photos", "queues"], "readonly", (tx, finish) => {
      const photo = tx.objectStore("photos").get([scope, key]);
      const queue = tx.objectStore("queues").get(scope);
      // Issued together in this transaction; both results are ready by its completion.
      queue.onsuccess = () => {
        const row = photo.result;
        const readyAt = row ? row.readyAt : Math.max(now, queue.result?.readyAt || 0) + PHOTO_DURATION_MS;
        finish({ recorded: Boolean(row), readyAt, remainingMs: Math.max(0, readyAt - now) });
      };
    });
  }

  function fileTime(key) {
    const match = /^(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})(?:_.*)?\.(?:jpe?g|png)$/i.exec(key.split("/").pop());
    if (!match) return null;
    const [, year, month, day, hour, minute, second] = match;
    const date = new Date(Date.UTC(Number(year), Number(month) - 1, Number(day), Number(hour), Number(minute), Number(second)));
    if (date.getUTCFullYear() !== Number(year) || date.getUTCMonth() + 1 !== Number(month) ||
        date.getUTCDate() !== Number(day) || date.getUTCHours() !== Number(hour) ||
        date.getUTCMinutes() !== Number(minute) || date.getUTCSeconds() !== Number(second)) return null;
    return `${day}/${month}/${year} ${hour}:${minute}:${second}`;
  }

  window.PrintHistory = { record, list, estimate, fileTime };
})();
