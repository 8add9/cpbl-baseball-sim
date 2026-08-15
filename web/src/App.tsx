import { useState } from 'react'
import { CareerMode } from './components/CareerMode'
import { ManagerMode } from './components/ManagerMode'

export function App() {
  const [mode, setMode] = useState<'career' | 'manager'>('manager')

  if (mode === 'career') {
    return <CareerMode onBack={() => setMode('manager')} />
  }
  return <ManagerMode onCareer={() => setMode('career')} />
}
