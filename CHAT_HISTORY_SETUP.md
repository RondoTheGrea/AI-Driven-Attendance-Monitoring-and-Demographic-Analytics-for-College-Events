# Chat History Implementation Guide

## Overview
Chat history functionality has been added to the AI Insights chat interface. This includes:
- **Frontend persistence** using localStorage (works immediately)
- **Backend storage** in database (requires migration)
- **Context for n8n** - conversation history is sent to n8n for better AI responses

## What Was Added

### 1. Database Model (`main/models.py`)
- Added `ChatMessage` model to store chat history
- Stores: message text, sender (user/bot), session ID, timestamps
- Indexed for efficient queries

### 2. Frontend Changes (`org/templates/org/insights/insights.html`)
- **localStorage integration**: Messages automatically saved to browser storage
- **History loading**: Chat history loads when page refreshes
- **Clear Chat button**: Users can clear their chat history
- **Message persistence**: All messages persist across page refreshes

### 3. Backend Changes (`org/views.py`)
- **Message saving**: Both user and bot messages saved to database
- **History retrieval**: Last 10 messages retrieved for context
- **n8n integration**: Conversation history sent to n8n webhook

## Setup Instructions

### Step 1: Run Database Migration
Since we added a new model, you need to create and run migrations:

```bash
python manage.py makemigrations
python manage.py migrate
```

### Step 2: Update n8n Workflow (Optional but Recommended)
Your n8n webhook now receives a `conversation_history` array with the format:

```json
{
  "message": "Current user message",
  "sessionId": "uuid-here",
  "organization_id": 1,
  "organization_name": "Organization Name",
  "user_id": 1,
  "conversation_history": [
    {
      "role": "user",
      "content": "Previous user message"
    },
    {
      "role": "assistant",
      "content": "Previous bot response"
    },
    {
      "role": "user",
      "content": "Current user message"
    }
  ]
}
```

**In your n8n workflow:**
- You can use the `conversation_history` array to provide context to your AI model
- This helps the AI maintain conversation context across messages
- If your AI supports conversation history, pass the entire array to it

### Step 3: Test the Feature
1. Open the AI Insights tab
2. Send a few messages
3. Refresh the page - messages should persist
4. Try the "Clear Chat" button

## How It Works

### Frontend (localStorage)
- Messages are stored in browser's localStorage
- Key: `ai_insights_chat_history`
- Automatically loads when page loads
- Limited to last 100 messages (prevents storage issues)

### Backend (Database)
- Messages saved to `ChatMessage` table
- Organized by user and session ID
- Last 10 messages retrieved for n8n context
- Persistent across browser sessions

### Session Management
- Each user session gets a unique `session_id`
- Stored in Django session
- Persists across page loads for same user session
- New session = new chat history

## Features

### ✅ Automatic History Loading
When you open the chat, all previous messages load automatically.

### ✅ Cross-Session Persistence
- Database stores messages permanently
- localStorage provides instant access
- Works even if you close and reopen the browser

### ✅ Clear Chat Functionality
- "Clear Chat" button in header
- Clears localStorage
- Database records remain (for analytics)

### ✅ Context for AI
- Last 10 messages sent to n8n
- Helps AI maintain conversation context
- Better responses with conversation awareness

## Troubleshooting

### Messages not persisting?
1. Check browser console for errors
2. Ensure localStorage is enabled in browser
3. Check database migration was run

### History not loading?
1. Clear browser cache
2. Check browser's localStorage
3. Verify database has messages (Django admin)

### n8n not receiving history?
- Check n8n workflow logs
- Verify `conversation_history` field in webhook payload
- Ensure n8n workflow can handle the array format

## Database Schema

The `ChatMessage` model includes:
- `user` - ForeignKey to User
- `organization` - ForeignKey to Organization  
- `message` - Text content
- `is_user_message` - Boolean (True for user, False for bot)
- `session_id` - CharField for session tracking
- `created_at` - Timestamp

## Future Enhancements (Optional)

1. **Export chat history** - Download chat as text/PDF
2. **Search chat history** - Search through past conversations
3. **Multiple chat sessions** - Allow users to create named chat sessions
4. **Chat analytics** - Track popular queries, response times
5. **Database cleanup** - Auto-delete old messages after X days

## Notes

- localStorage is per-browser/device
- Database storage is per-user across devices
- Session ID persists for Django session lifetime
- Messages older than 100 in localStorage are automatically trimmed
