export interface User {
  id: string
  username: string
  password: string
  role: 'admin' | 'user'
  name: string
  phone: string
}

export interface Field {
  id: string
  name: string
  area: number
  bounds: [number, number][]
  ownerId: string | null
  crop: string | null
  growthStage: string | null
  plantDate: string | null
}

export interface IrrigationRecord {
  fieldId: string
  date: string
  predicted: number
  actual: number | null
  stage: string
}

export interface WeatherStatus {
  lastUpdate: string
  temperature: number
  humidity: number
  rainfall: number
  status: 'normal' | 'warning'
}

export interface AuthState {
  user: Omit<User, 'password'> | null
  token: string | null
}
