import { useEffect } from "react";
import { useAuthStore, useChatStore } from "./lib/store";
import LoginView from "./components/LoginView";
import Layout from "./components/Layout";

export default function App() {
  const { isAuthenticated, isLoading, checkAuth } = useAuthStore();
  const { loadConfig, loadDocuments } = useChatStore();

  useEffect(() => {
    checkAuth();
    loadConfig();
  }, [checkAuth, loadConfig]);

  // Load documents only after authentication
  useEffect(() => {
    if (isAuthenticated) {
      loadDocuments();
    }
  }, [isAuthenticated, loadDocuments]);

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="flex gap-1.5">
          <span className="loading-dot h-2 w-2 rounded-full bg-teal-500" />
          <span className="loading-dot h-2 w-2 rounded-full bg-teal-500" />
          <span className="loading-dot h-2 w-2 rounded-full bg-teal-500" />
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <LoginView />;
  }

  return <Layout />;
}
