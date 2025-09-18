# Overview

This is a Discord bot designed for Roblox group management and verification. The bot provides functionality to bind Discord roles to Roblox group ranks, verify users against their Roblox profiles, and manage group member rankings through Discord commands. It integrates with the Roblox API to fetch group information and user data, enabling seamless synchronization between Discord server roles and Roblox group positions.

# User Preferences

Preferred communication style: Simple, everyday language.

# System Architecture

## Bot Framework
- **Discord.py**: Core Discord bot framework with application commands (slash commands) support
- **Asynchronous Architecture**: Built on asyncio for handling concurrent Discord and Roblox API operations
- **Command System**: Uses both traditional prefix commands and modern slash commands for user interaction

## Data Persistence
- **JSON File Storage**: Simple file-based storage for configuration data
  - `rank_binds.json`: Maps Roblox group ranks to Discord role IDs
  - `verified_users.json`: Stores Discord-to-Roblox user verification mappings
- **In-Memory Caching**: Group roles cached in memory for performance optimization

## Configuration Management
- **Environment Variables**: Sensitive data stored in `.env` file
  - Discord bot token
  - Roblox authentication cookie
  - Webhook URLs for logging
  - Group ID and allowed role permissions
- **Dynamic Configuration**: Rank bindings configurable through bot commands

## Permission System
- **Role-Based Access Control**: Commands restricted to users with specific Discord roles
- **Administrative Controls**: Sensitive operations require elevated permissions
- **Group Integration**: Permissions validated against both Discord roles and Roblox group positions

## API Integration Architecture
- **Roblox API Client**: Custom HTTP client using aiohttp for Roblox web API interactions
- **Authentication**: Cookie-based authentication for Roblox API access
- **Rate Limiting**: Designed to respect API rate limits through asynchronous request handling

## Deployment Architecture
- **Flask Web Server**: Embedded web server for health checks and potential webhook endpoints
- **Multi-Threading**: Flask server runs on separate thread from Discord bot
- **Replit Compatibility**: Structured for cloud deployment on Replit platform

# External Dependencies

## Core Libraries
- **discord.py**: Discord API wrapper for bot functionality
- **aiohttp**: Asynchronous HTTP client for Roblox API requests
- **Flask**: Web framework for server endpoints
- **python-dotenv**: Environment variable management

## Roblox Services
- **Roblox Web API**: User profile and group data retrieval
- **Group Management API**: Member ranking and role verification
- **Authentication System**: Cookie-based session management

## Discord Services
- **Discord Bot API**: Message handling and command processing
- **Discord Webhooks**: Logging and notification system
- **Role Management**: Automated role assignment based on Roblox ranks

## Environment Services
- **Replit Platform**: Cloud hosting and execution environment
- **File System**: Local JSON storage for persistent configuration data