# Brightwater Labs s.r.o. – IT Security Policy

| Item | Detail |
| --- | --- |
| Document ID | IT-POL-004 |
| Version | 3.0 |
| Effective from | 1 May 2026 |
| Owner | Information Security Officer |
| Contact | security@brightwater.example |

This policy is a fictional document written for software testing.

## 1. Purpose and scope

This policy sets the minimum security rules for using Brightwater information systems.
It applies to all employees, contractors and visitors who use company devices, accounts or networks.
Breaking this policy may lead to disciplinary action and to the loss of system access.
Exceptions to this policy must be approved in writing by the Information Security Officer.

## 2. Passwords and multi-factor authentication

### 2.1 Passwords

Passwords must be at least 14 characters long.
Use a passphrase of several unrelated words rather than a single complex word.
Never reuse a Brightwater password for any private account or other service.
Passwords do not expire on a schedule, but must be changed at once if you suspect someone knows them.
Store passwords only in the company password manager, never in documents, notes or browsers.
An account is locked for 15 minutes after 10 failed sign-in attempts.

### 2.2 Multi-factor authentication

Multi-factor authentication (MFA) is required for email, VPN and every system reachable from the internet.
The approved MFA methods are the Brightwater Authenticator app and a company-issued hardware security key.
One-time codes sent by SMS are not accepted as a second factor.
Never approve an MFA prompt that you did not start yourself, and report any such prompt as an incident.

## 3. Devices

### 3.1 Company devices

Only company-managed laptops and phones may connect to the internal network.
Disk encryption must stay enabled on every laptop.
The screen locks automatically after 5 minutes of inactivity.
Lock the screen yourself whenever you leave the device, even for a moment.

### 3.2 Lost or stolen devices

A lost or stolen company laptop or phone must be reported to the IT Service Desk within 1 hour of noticing.
Call the Service Desk on +420 555 010 200, which is staffed 24 hours a day.
The Service Desk will lock the accounts on the device and wipe it remotely.
For a theft, also report it to the police and send the police reference number to the Service Desk.
Do not wait to see whether a lost device turns up before reporting it.

## 4. Remote access and VPN

The company VPN must be used for all access to internal systems from outside the office.
The VPN client starts automatically when a company laptop is outside the office network.
Public Wi-Fi networks may be used only with the VPN connected.
Split tunnelling is disabled, so all traffic goes through the company network while the VPN is on.
A VPN session is disconnected automatically after 12 hours and must then be started again.
Personal devices must not connect to the VPN.

## 5. Data classification

### 5.1 Classification levels

All company information is classified at one of four levels.

| Level | Description | Examples |
| --- | --- | --- |
| Public | Approved for publication | Press releases, published job adverts |
| Internal | For employees and contractors only | Intranet pages, internal procedures, org charts |
| Confidential | Limited to people who need it for their work | Contracts, budgets, unreleased product data |
| Strictly Confidential | Named people only; highest protection | Personal health data, clinical trial raw data |

### 5.2 Handling rules

Documents must show their classification in the header or footer.
Information without a label must be treated as Internal until its owner classifies it.
Confidential information may be shared outside the company only under a signed confidentiality agreement.
Strictly Confidential information must be encrypted both at rest and in transit.
Strictly Confidential information must never be sent by email outside the company.
Printed Confidential and Strictly Confidential documents are destroyed in the locked shredding bins.

## 6. Removable media

USB storage devices are blocked on company laptops by default.
Only encrypted USB drives issued by the IT Service Desk may be used, and only after an exception is approved.
Exceptions are approved by the Information Security Officer for a maximum of 90 days.
Strictly Confidential information must never be copied to removable media.
Found or unknown USB devices must be handed to the Service Desk and never plugged in.

## 7. Phishing and suspicious messages

Report suspicious emails with the Report Phishing button in the mail client.
If the button is not available, forward the email as an attachment to phishing@brightwater.example.
Do not click links, open attachments or reply to a suspicious message.
If you have already clicked a link or entered your password, call the Service Desk immediately.
The security team runs phishing simulation campaigns every quarter.
Employees who report a simulated phishing email receive a confirmation and no further action is needed.

## 8. Software installation

Users do not have administrator rights on company laptops by default.
Software may be installed only from the Brightwater Software Center.
Software that is not in the Software Center can be requested through the Service Desk.
The IT team reviews each request for security and licensing within 5 working days.
Browser extensions are allowed only from the approved list on the intranet.
Pirated, cracked or unlicensed software is forbidden on all company devices.

## 9. Logging and monitoring

Company systems record security events so that incidents can be detected and investigated.
Logs are protected against change and can be read only by the security team and auditors.
Logs are retained for the following periods.

| Log type | Retention period |
| --- | --- |
| Security event logs | 12 months |
| VPN connection logs | 6 months |
| Web proxy logs | 3 months |
| Email gateway logs | 3 months |
| Audit trails of GxP systems | As set in the GxP records retention schedule |

After the retention period, logs are deleted automatically unless they are needed for an investigation.

## 10. Reporting security incidents

Report any suspected security incident to security@brightwater.example or to the Service Desk.
Examples include malware warnings, unexpected MFA prompts, data sent to the wrong person and lost devices.
Reporting quickly is always better than trying to fix the problem yourself.
No one is penalised for reporting an incident in good faith.

## 11. Contacts

| Topic | Contact |
| --- | --- |
| IT Service Desk | servicedesk@brightwater.example, +420 555 010 200 |
| Security incidents | security@brightwater.example |
| Phishing reports | phishing@brightwater.example |
| Information Security Officer | iso@brightwater.example |
