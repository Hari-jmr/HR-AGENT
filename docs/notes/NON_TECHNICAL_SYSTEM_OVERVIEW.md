# HR Assistant System Overview

## What this system is

This system is an internal HR assistant for employees and HR teams.

It helps users ask questions in simple language and get answers from the company HRMS data.

Examples:
- leave balance
- latest salary summary
- attendance summary
- manager name
- department details
- expense or timesheet details

## What the user sees

A user opens the HR Assistant screen and signs in.

After login, they can type a question like they are chatting with a person.

The system then reads the question, checks the user session, finds the correct data, and gives a reply in a simple chat format.

## How it works in simple steps

### 1. User signs in
The user enters username and password.

The system checks those details against the HRMS user records.

If valid:
- the user is logged in
- the employee profile is loaded
- the system knows whether the person is a normal employee or HR user

### 2. User asks a question
The user types a question in the chat box.

For example:
- Show my leave balance
- What was my latest payroll summary?
- Who is my manager?

### 3. The system understands the type of question
The system checks what kind of question it is.

Usually it falls into one of these groups:
- leave
- payroll
- attendance
- timesheet
- expenses
- employee details
- policy question

### 4. The system decides how to answer
There are two main ways it answers.

#### A. Fixed answer path for common questions
For very common questions like leave balance or latest payroll summary, the system uses a direct and reliable path.

This means it already knows exactly where to look in the database and how to prepare the answer.

This is faster and more accurate for those common questions.

#### B. Smart database search for broader questions
For other live HR data questions, the system converts the question into a safe database query.

Then it reads the required data and turns it into a user-friendly answer.

## Important safety rule

The system is read-only.

That means it can only read data.

It does not change employee records, update payroll, approve leave, or write anything back into the HRMS database.

## How user access is controlled

### Normal employee
A normal employee should only see their own data.

Examples:
- my leave balance
- my salary summary
- my attendance
- my manager

### HR user
An HR user can ask broader questions depending on their access.

Examples:
- attendance summary for a team
- latest payroll details for an employee
- employee listing by department

## What the system is good at right now

It works best for live HRMS data questions such as:
- leave balances
- payroll summary
- attendance summary
- timesheet details
- expense claims
- employee master details

## What it does not really answer right now

It does not currently have a live policy document library connected.

So if someone asks about policy rules or handbook details, the system will usually say:
- contact HR for details

Examples:
- travel policy
- insurance policy rules
- leave encashment rules
- how to do something in ERP if that depends on guide documents

## Why some questions work better than others

The best questions are:
- short
- clear
- about one topic
- based on live employee data

Good examples:
- Show my leave balance
- What is my latest net pay?
- Summarize my attendance for the last 30 days
- Who is my reporting manager?

Less reliable examples:
- Explain all company policies
- Tell me every rule related to travel, resignation, insurance, and bonus
- How do I do every HR process in ERP

## Simple end-to-end flow

1. User logs in.
2. System identifies the employee.
3. User asks a question.
4. System decides what kind of question it is.
5. System reads the required HRMS data safely.
6. System formats the answer.
7. User sees the response in chat.

## Example questions employees can ask

- Show my leave balance
- How many casual leave days do I have?
- What was my latest payroll summary?
- What is my current net pay?
- Summarize my attendance for the last 30 days
- Who is my manager?
- What is my department?
- Show my recent expense claims
- Show my latest timesheet

## Example questions HR can ask

- Show attendance summary for a department
- Show latest payroll summary for an employee
- List employees who joined recently
- Show timesheet status for a team
- Show recent expense claims by employee

## In one line

This system is a chat-based HR assistant that safely reads HRMS data and gives users simple answers based on their access level.
