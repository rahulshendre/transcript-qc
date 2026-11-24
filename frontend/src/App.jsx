import React, { useState } from "react";
import Review from "./Review.jsx";
import Upload from "./Upload.jsx";

export default function App() {
  const [session, setSession] = useState(null);
  return session ? (
    <Review key={session.id} initial={session} onClose={() => setSession(null)} />
  ) : (
    <Upload onOpen={setSession} />
  );
}
