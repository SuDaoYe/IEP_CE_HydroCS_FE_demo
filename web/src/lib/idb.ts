import { openDB, type DBSchema, type IDBPDatabase } from 'idb'
import type { Field, PendingOp } from '../types'

interface HydroDB extends DBSchema {
  fields: { key: string; value: Field }
  pending: { key: string; value: PendingOp }
  meta: { key: string; value: string }
}

let dbPromise: Promise<IDBPDatabase<HydroDB>> | null = null

function getDB() {
  if (!dbPromise) {
    dbPromise = openDB<HydroDB>('hydrocs', 1, {
      upgrade(db) {
        if (!db.objectStoreNames.contains('fields')) db.createObjectStore('fields', { keyPath: 'id' })
        if (!db.objectStoreNames.contains('pending'))
          db.createObjectStore('pending', { keyPath: 'op_id' })
        if (!db.objectStoreNames.contains('meta')) db.createObjectStore('meta')
      },
    })
  }
  return dbPromise
}

export const offline = {
  async putFields(fields: Field[]) {
    const db = await getDB()
    const tx = db.transaction('fields', 'readwrite')
    await Promise.all(fields.map((field) => tx.store.put(field)))
    await tx.done
  },

  async putField(field: Field) {
    const db = await getDB()
    await db.put('fields', field)
  },

  async dropField(id: string) {
    const db = await getDB()
    await db.delete('fields', id)
  },

  async allFields(): Promise<Field[]> {
    const db = await getDB()
    return db.getAll('fields')
  },

  async enqueue(op: PendingOp) {
    const db = await getDB()
    await db.put('pending', op)
  },

  async pending(): Promise<PendingOp[]> {
    const db = await getDB()
    return db.getAll('pending')
  },

  async removeOps(ids: string[]) {
    const db = await getDB()
    const tx = db.transaction('pending', 'readwrite')
    await Promise.all(ids.map((id) => tx.store.delete(id)))
    await tx.done
  },

  async setMeta(key: string, value: string) {
    const db = await getDB()
    await db.put('meta', value, key)
  },

  async getMeta(key: string): Promise<string | undefined> {
    const db = await getDB()
    return db.get('meta', key)
  },

  async clear() {
    const db = await getDB()
    await Promise.all([db.clear('fields'), db.clear('pending')])
  },
}
