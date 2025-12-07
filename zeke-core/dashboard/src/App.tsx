import { Routes, Route } from 'react-router-dom';
import { Layout } from './components/Layout';
import { Dashboard } from './pages/Dashboard';
import { Chat } from './pages/Chat';
import { Memories } from './pages/Memories';
import { Tasks } from './pages/Tasks';
import { Curation } from './pages/Curation';

function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="chat" element={<Chat />} />
        <Route path="memories" element={<Memories />} />
        <Route path="tasks" element={<Tasks />} />
        <Route path="curation" element={<Curation />} />
      </Route>
    </Routes>
  );
}

export default App;
