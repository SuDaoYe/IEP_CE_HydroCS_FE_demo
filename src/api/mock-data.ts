import type { User, Field, IrrigationRecord, WeatherStatus } from '../types'

export const users: User[] = [
  { id: 'u1', username: 'admin', password: 'admin123', role: 'admin', name: '管理员', phone: '13800000000' },
  { id: 'u2', username: 'farmer1', password: '123456', role: 'user', name: '张农户', phone: '13800000001' },
  { id: 'u3', username: 'farmer2', password: '123456', role: 'user', name: '李农户', phone: '13800000002' },
]

export const fields: Field[] = [
  { id: 'f1', name: '田块 A-01', area: 2.3, bounds: [[30.25, 120.15], [30.26, 120.15], [30.26, 120.16], [30.25, 120.16]], ownerId: 'u2', crop: '小麦', growthStage: '拔节期', plantDate: '2026-03-15' },
  { id: 'f2', name: '田块 A-02', area: 1.8, bounds: [[30.25, 120.17], [30.26, 120.17], [30.26, 120.18], [30.25, 120.18]], ownerId: 'u2', crop: '玉米', growthStage: '抽穗期', plantDate: '2026-05-01' },
  { id: 'f3', name: '田块 B-01', area: 3.1, bounds: [[30.27, 120.15], [30.28, 120.15], [30.28, 120.16], [30.27, 120.16]], ownerId: 'u3', crop: '水稻', growthStage: '分蘖期', plantDate: '2026-04-10' },
  { id: 'f4', name: '田块 B-02', area: 2.7, bounds: [[30.27, 120.17], [30.28, 120.17], [30.28, 120.18], [30.27, 120.18]], ownerId: 'u3', crop: '小麦', growthStage: '灌浆期', plantDate: '2026-02-20' },
  { id: 'f5', name: '田块 C-01', area: 1.5, bounds: [[30.29, 120.15], [30.30, 120.15], [30.30, 120.16], [30.29, 120.16]], ownerId: null, crop: null, growthStage: null, plantDate: null },
  { id: 'f6', name: '田块 C-02', area: 4.2, bounds: [[30.29, 120.17], [30.30, 120.17], [30.30, 120.18], [30.29, 120.18]], ownerId: null, crop: null, growthStage: null, plantDate: null },
]

export const irrigationRecords: IrrigationRecord[] = [
  { fieldId: 'f1', date: '2026-06-10', predicted: 320, actual: null, stage: '拔节期' },
  { fieldId: 'f1', date: '2026-06-17', predicted: 380, actual: null, stage: '拔节期' },
  { fieldId: 'f2', date: '2026-06-10', predicted: 450, actual: null, stage: '抽穗期' },
  { fieldId: 'f2', date: '2026-06-17', predicted: 520, actual: null, stage: '抽穗期' },
  { fieldId: 'f3', date: '2026-06-10', predicted: 280, actual: null, stage: '分蘖期' },
  { fieldId: 'f4', date: '2026-06-10', predicted: 400, actual: null, stage: '灌浆期' },
]

export const weatherStatus: WeatherStatus = {
  lastUpdate: '2026-06-10T08:00:00',
  temperature: 28.5,
  humidity: 65,
  rainfall: 12.3,
  status: 'normal',
}
