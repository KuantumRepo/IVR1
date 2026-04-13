"use client";

import { useRouter } from "next/navigation";

export default function DeleteListButton({ listId }: { listId: string }) {
  const router = useRouter();

  const handleDelete = async () => {
      if (!confirm("Are you sure you want to delete this list?")) return;
      try {
          const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || '/api/v1'}/contact-lists/${listId}`, {
              method: 'DELETE'
          });
          if (!res.ok) throw new Error("Failed to delete");
          router.refresh();
      } catch (e) {
          alert("Failed to delete list");
      }
  };

  return (
    <button onClick={handleDelete} className="text-xs font-medium text-destructive-foreground hover:text-red-400 transition-colors">
      Delete
    </button>
  );
}
