"use client";
import { useEffect, useLayoutEffect, useRef, useState } from "react";

/** Loads `fn()` on mount and whenever `deps` change. `reload()` refetches without clearing data. */
export function useApi<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(true);
  const [version, setVersion] = useState(0);
  const latest = useRef(fn);
  useLayoutEffect(() => {
    latest.current = fn;
  });

  const depsKey = JSON.stringify(deps);
  useEffect(() => {
    let cancelled = false;
    latest
      .current()
      .then((value) => {
        if (!cancelled) {
          setData(value);
          setError(null);
        }
      })
      .catch((err) => !cancelled && setError(err))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [depsKey, version]);

  const reload = () => {
    setLoading(true);
    setVersion((v) => v + 1);
  };

  return { data, error, loading, reload, setData };
}
