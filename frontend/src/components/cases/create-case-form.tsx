"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Plus } from "lucide-react";

interface CreateCaseFormProps {
  onSubmit: (data: {
    name: string;
    input: string;
    expected_output: string;
    tags: string[];
  }) => void;
}

export function CreateCaseForm({ onSubmit }: CreateCaseFormProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [name, setName] = useState("");
  const [input, setInput] = useState("");
  const [expectedOutput, setExpectedOutput] = useState("");
  const [tags, setTags] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !input.trim() || !expectedOutput.trim()) return;
    onSubmit({
      name: name.trim(),
      input: input.trim(),
      expected_output: expectedOutput.trim(),
      tags: tags.split(",").map((t) => t.trim()).filter(Boolean),
    });
    setName("");
    setInput("");
    setExpectedOutput("");
    setTags("");
    setIsOpen(false);
  };

  if (!isOpen) {
    return (
      <Button onClick={() => setIsOpen(true)} variant="outline">
        <Plus className="mr-2 h-4 w-4" />
        Add Test Case
      </Button>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">New Test Case</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-3">
          <Input
            placeholder="Case name"
            value={name}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setName(e.target.value)}
          />
          <Textarea
            placeholder="Input (what to send to the agent)"
            value={input}
            onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setInput(e.target.value)}
            rows={2}
          />
          <Textarea
            placeholder="Expected output (what the agent should respond)"
            value={expectedOutput}
            onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setExpectedOutput(e.target.value)}
            rows={2}
          />
          <Input
            placeholder="Tags (comma-separated)"
            value={tags}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setTags(e.target.value)}
          />
          <div className="flex gap-2">
            <Button type="submit" size="sm">
              Create
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => setIsOpen(false)}
            >
              Cancel
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
