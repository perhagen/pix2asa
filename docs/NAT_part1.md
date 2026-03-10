NAT Configuration on ASA 8.4+, Part 1
​
 Summarize
​
04 // 02 // 15
NetCraftsmen®

Series: NAT Configuration on ASA 8.4+

Part 1: Introduction and NAT Rule Organization
Part 3: Dynamic PAT Cont. with Pools, Flat, Round-Robin and Extended PAT
Part 4: Dynamic PAT With and Without Fallback
Note: This post was edited by Marilyn Outerbridge

At the initial rollout of ASA 8.3/8.4, one of the first things network engineers noticed was that the NAT configuration on the new code had changed drastically. The main concern was how one would upgrade ASA devices from a pre-8.3/8.4 code to a newer code. What would be the side effects of the upgrade; and most importantly, what functionality may “break” as a result?

Fast forward to 2015, ASA 8.2 upgrades to 8.4+ code should (hopefully) be less of a concern for engineers than deploying new firewalls with the current ASA code (8.4+). This series of blog posts will be a little different than most others on ASA 8.4 NAT. It will not look at the past or provide a way to migrate from older versions of ASA. The pertinent information is probably still here but the idea is to discuss the ASA 8.4+ NAT (hereafter called ASA NAT or just NAT) as independently as possible. As always, some comparisons will be too tempting to pass over.

With the introduction out of the way, it is time to take a look at NAT operations and the configuration of NAT on the ASA.

NAT Sections

The order of how an incoming or outgoing packet is matched against the NAT statements or rules is of utmost importance. To maintain order and determinism, ASA allots each configured NAT rule into one of the three sections:

Section 1 – Manual NAT
Also called Twice NAT
Section 2 – Auto NAT
Also called Network Object NAT
Hereafter NON in the blog post
Section 3 – Manual NAT
Also called Manual NAT After Auto NAT
Also called Twice NAT After Auto NAT
Though this may look confusing at the outset, it is actually quite straightforward, providing the user much granularity when it comes to NAT configuration.

Essentially, any ingress packet is compared against the NAT rules configured on the firewall. The sections are extremely important because they determine the overarching order in which the packet will be matched against the configured rules.

The packet is first matched against each and every rule in Section 1. If it does not match any of the rules, it is then matched against each rule in Section 2. If there is still no match, the packet is further compared to each of the rules in Section 3. If a match again is not made, the packet is sent through without any NAT operations performed on it. Since the concept of nat-control is now archaic, it is in fact possible for the packet to pass through the ASA untouched by NAT rules.

Finally, there is an order to the statements or rules within the sections. The order of policies within each section is determined differently depending on which section the NAT statement is configured in. Ergo, it becomes important to understand the ordering of the rules inside the three sections.

Section 1

The rules in Section 1 have a line number associated with them. Just like an ASA ACL, a new rule configured with the same line number of a current rule will take that position and push (increment) every rule below that position by one number. Hence a rule inserted at position 3 will reorder the previous rules numbered 3, 4 and 5 to 4, 5 and 6.

Section 2

The concept of line numbers does not exist in Section 2 (Auto NAT or Network Object NAT section). The rules in this section are arranged automatically according to their type.

A static NAT rule is always preferred over a dynamic NAT rule. Thus, all the static NAT rules are encountered before all dynamic NAT rules.

Next comes the organization within these static and dynamic “subsections.”

One has to keep in mind that this section only contains source IP NAT rules. The ASA is therefore able to utilize the size of the configured real IP blocks to further order the rules. Blocks containing fewer numbers of real IPs float to the top of each sub-section (static and dynamic) followed by ever increasing block sizes.

As an example, a static NAT rule that translates the 192.168.13.0/26 will appear before a static NAT rule that translates the 192.168.13.0/24 block to an IP. This same example can be used for dynamic NAT rules.

Not that it matters, but blocks with identical sizes are arranged from lowest to highest numerically. Hence, 192.168.1.0/24 is placed before 192.168.2.0/24

Section 3

This section is identical to Section 1 in every way except for the fact that it has a lower preference than Section 2. As in Section 1, there is a line number associated with each rule in this section. The user can configure the line number for each rule in the CLI to create an ordered list of NAT statements the packet is matched against.

The Right Section for a NAT Statement

This decision is probably the most important decision of an ASA NAT administrator. And this is the one aspect where ASA 8.4+ code provides far greater granularity than the pre-8.3 code. In the 8.4+ code, any NAT statement can be inserted virtually anywhere in the hierarchy and one can literally micro-manage the NAT order of operations. The only restriction that the ASA seems to put on the configuration is the following:

The Policy NAT feature of ASA pre-8.3 can only be mimicked correctly in Section 1 or Section 3, i.e. only via Twice or Manual NAT
Most other types of NAT can be implemented either via Twice NAT or Network Object NAT although Twice NAT is the easier of the two for nearly all but one scenario (almost all of these scenarios will be covered by future blogs post in this series). Thus, the decision of where to place the NAT statement is left to the ASA NAT administrator. It is more an exercise in logic than anything else. The current NAT policies already configured on the ASA must be carefully examined to determine where to place the new NAT statement. This can be done by comparing the interesting traffic against all the existing rules. This part requires expertise and a deep understanding of NAT but not necessarily of the intricacies of the internal order of operations that was crucial to NAT configuration on pre-8.3 code.

Although further blogs in this series will go through various NAT scenarios, to close out the first blog post of the series, here is a look at what a fully configured ASA, with rules in every single NAT section would look like:

ASA1(config)# show nat detail
Manual NAT Policies (Section 1)
1 (inside) to (outside) source dynamic obj_192.168.13.0 interface
  translate_hits = 0, untranslate_hits = 0
  Source - Origin: 192.168.13.0/24, Translated: 192.168.23.3/24
2 (inside) to (dmz1) source dynamic obj_192.168.13.0 interface
  translate_hits = 0, untranslate_hits = 0
  Source - Origin: 192.168.13.0/24, Translated: 192.168.34.3/24

Auto NAT Policies (Section 2)
1 (inside) to (dmz1) source dynamic obj_192.168.13.0_dmz1 interface
  translate_hits = 1, untranslate_hits = 0
  Source - Origin: 192.168.13.0/24, Translated: 192.168.34.3/24
2 (inside) to (outside) source dynamic obj_192.168.13.0_outside interface
  translate_hits = 3, untranslate_hits = 0
  Source - Origin: 192.168.13.0/24, Translated: 192.168.23.3/24

Manual NAT Policies (Section 3)
1 (inside) to (outside) source dynamic obj_192.168.13.0 interface
  translate_hits = 0, untranslate_hits = 0
  Source - Origin: 192.168.13.0/24, Translated: 192.168.23.3/24
2 (inside) to (dmz1) source dynamic obj_192.168.13.0 interface
  translate_hits = 0, untranslate_hits = 0
  Source - Origin: 192.168.13.0/24, Translated: 192.168.34.3/24
NetCraftsmen®

Note: This post was edited by Marilyn Outerbridge

This is a second blog post of a series. For the series, please click here.
This blog post will cover all of the major Dynamic PAT “flavors” that one might encounter in production networks and some that may show up on the CCIE lab. A detailed explanation of the applicability in production of the scenario being discussed is deemed outside the scope of this series. Most ASA books pre 8.4 cover those aspects in much detail. The reader is encouraged to reference one of these books.

The NAT examples in the article are taken from the following topology:

ASA Nat Topology

Figure 2-1: ASA NAT Topology

Generally, in production networks, more than two interfaces exist. The configuration examples herein assume that either 2+ interfaces are already in use, or will be used in the future, making it somewhat future-proof.

Without further ado, here are the major NAT types and sub-types that most scenarios fit into.

Dynamic NAT
Static NAT
Identity NAT
NAT Exemption
Dynamic NAT

Dynamic NAT on the ASA can be configured to appear in any of the three sections discussed in Part 1. That, combined with the fact that there are various types of Dynamic PAT applicable to a scenario makes for a decent size list.

Dynamic PAT to ASA Interface IP Address

In the most simplistic case, a block of IP addresses residing on the Inside interface will be translated either to the ASA Outside or DMZ interface address.

The keyword any cannot be used for the external interface if the mapped IP is the interface IP. One NAT statement (NON or Twice NAT) for each external interface must be configured.
Using Network Object NAT (NON)

With Auto NAT or NON, an object would have to be created for each interface where the rule is applied.

In the example topology, the ASA is translating the inside IP block, 192.168.13/24 to the Gi0/0 IP for traffic leaving the outside interface and to the Gi0/2 IP for traffic leaving the DMZ1 interface.

Configuration

ASA1(config)# object network obj_192.168.13.0_outside
ASA1(config-network-object)# subnet 192.168.13.0 255.255.255.0
ASA1(config-network-object)# nat (inside,outside) dynamic interface
ASA1(config-network-object)#exit
ASA1(config)# object network obj_192.168.13.0_dmz1
ASA1(config-network-object)# subnet 192.168.13.0 255.255.255.0
ASA1(config-network-object)# nat (inside,dmz1) dynamic interface

Verification

ASA1# sho run object
object network obj_192.168.13.0_outside
 subnet 192.168.13.0 255.255.255.0
object network obj_192.168.13.0_dmz1
 subnet 192.168.13.0 255.255.255.0

ASA1# sho run nat
!
object network obj_192.168.13.0_outside
 nat (inside,outside) dynamic interface
object network obj_192.168.13.0_dmz1
 nat (inside,dmz1) dynamic interface

ASA1# sho nat detail

Auto NAT Policies (Section 2)
1 (inside) to (dmz1) source dynamic obj_192.168.13.0_dmz1 interface 
 translate_hits = 0, untranslate_hits = 0
 Source - Origin: 192.168.13.0/24, Translated: 192.168.34.3/24
2 (inside) to (outside) source dynamic obj_192.168.13.0_outside interface 
 translate_hits = 0, untranslate_hits = 0
 Source - Origin: 192.168.13.0/24, Translated: 192.168.23.3/24
This illustrates the two different types of NAT verification on the ASA. Essentially, the show run object is for configuration verification whereas show nat gives an insight into the operation of the ASA.

Caveat: Note that during configuration, the IP block of the object as well as the NAT operations are configured at the same time, seemingly under the same object group. But the ASA actually stores the code in two different sections, albeit under the same parent category - i.e. the object network category.

Thus, the IP block definition is stored with the other objects and object-groups but the NAT portion is stored under an object with the same name in the NAT portion of the configuration.

This can make the configuration verification a bit tedious and unintuitive for some.
Finally, the packet tracer verification will identify the exact rule used to translate the packet.

Packet Tracer Verification

ASA1# packet-tracer input inside tcp 192.168.13.1 10000 192.168.23.2 23

Phase: 1
Type: ROUTE-LOOKUP
Subtype: input
Result: ALLOW
Config:
Additional Information:
in   192.168.23.0    255.255.255.0   outside

Phase: 2
Type: IP-OPTIONS
Subtype:
Result: ALLOW
Config:
Additional Information:

Phase: 3
Type: NAT
Subtype:
Result: ALLOW
Config:
object network obj_192.168.13.0_outside
  nat (inside,outside) dynamic interface
Additional Information:
Dynamic translate 192.168.13.1/10000 to 192.168.23.3/16014

Phase: 4
Type: IP-OPTIONS
Subtype:
Result: ALLOW
Config:
Additional Information:

Phase: 5
Type: FLOW-CREATION
Subtype:
Result: ALLOW
Config:
Additional Information:
New flow created with id 5, packet dispatched to next module

Result:
input-interface: inside
input-status: up
input-line-status: up
output-interface: outside
output-status: up
output-line-status: up
Action: allow
The result of this configuration is visible when R1 makes a TCP connection to R2 or R3.

Results
R1#telnet 192.168.23.2
Trying 192.168.23.2 ... Open

R2#who
Line         User    Host(s)     Idle       Location
0 con 0              idle       00:31:42
* 98 vty 0           idle       00:00:00   192.168.23.3

Interface    User        Mode         Idle     Peer Address 

R2#exit

[Connection to 192.168.23.2 closed by foreign host]
R1#telnet 192.168.34.4
Trying 192.168.34.4 ... Open

R4#who
Line         User    Host(s)     Idle       Location
0 con 0               idle     00:30:01
* 98 vty 0            idle     00:00:00     192.168.34.3

Interface    User        Mode         Idle     Peer Address 
USING MANUAL OR TWICE NAT

For Twice NAT, a single object can be defined for the source IP or IP block. Having said that, two NAT statements will still exist to perform the actual NAT as the keyword any is not allowed as per the note at the beginning of the section.

Configuration

ASA1(config)# object network obj_192.168.13.0
ASA1(config-network-object)# subnet 192.168.13.0 255.255.255.0
ASA1(config-network-object)# exit
ASA1(config)# nat (inside,outside) source dynamic obj_192.168.13.0 interface
ASA1(config)# nat (inside,dmz1) source dynamic obj_192.168.13.0 interface

Verification

ASA1(config)# show nat detail 
Manual NAT Policies (Section 1)
1 (inside) to (outside) source dynamic obj_192.168.13.0 interface  
    translate_hits = 0, untranslate_hits = 0
    Source - Origin: 192.168.13.0/24, Translated: 192.168.23.3/24
2 (inside) to (dmz1) source dynamic obj_192.168.13.0 interface  
    translate_hits = 0, untranslate_hits = 0
    Source - Origin: 192.168.13.0/24, Translated: 192.168.34.3/24

Auto NAT Policies (Section 2)
1 (inside) to (dmz1) source dynamic obj_192.168.13.0_dmz1 interface  
    translate_hits = 1, untranslate_hits = 0
    Source - Origin: 192.168.13.0/24, Translated: 192.168.34.3/24
2 (inside) to (outside) source dynamic obj_192.168.13.0_outside interface  
    translate_hits = 3, untranslate_hits = 0
    Source - Origin: 192.168.13.0/24, Translated: 192.168.23.3/24
The notable observation in the above output is that Section 1 was populated with the two new configured rules. Comparing it to the show nat detail output of NON section, notice there was no Section 1 (it is empty) in the NON only output. Now, Section 1 entries show up in the output before Section 2 entries. They also appear in the same order as they were configured on the CLI. Thus, the NAT rule order can be determined simply by looking at this output.
Once again, packet tracer will provide a definitive answer as to which rule is used for the actual translation:

Packet Tracer Verification

ASA1(config)# packet-tracer input inside tcp 192.168.13.1 10000 192.168.23.2 23

Phase: 1
Type: ROUTE-LOOKUP
Subtype: input
Result: ALLOW
Config:
Additional Information:
in   192.168.23.0    255.255.255.0   outside

Phase: 2
Type: IP-OPTIONS
Subtype: 
Result: ALLOW
Config:
Additional Information:

Phase: 3
Type: NAT
Subtype: 
Result: ALLOW
Config:
nat (inside,outside) source dynamic obj_192.168.13.0 interface
Additional Information:
Dynamic translate 192.168.13.1/10000 to 192.168.23.3/24233

Phase: 4      
Type: IP-OPTIONS
Subtype: 
Result: ALLOW
Config:
Additional Information:

Phase: 5
Type: FLOW-CREATION
Subtype: 
Result: ALLOW
Config:
Additional Information:
New flow created with id 8, packet dispatched to next module

Result:
input-interface: inside
input-status: up
input-line-status: up
output-interface: outside
output-status: up
output-line-status: up
Action: allow
As the packet tracer output shows, the packet is being translated by the Twice NAT rules.

Results
R1#telnet 192.168.23.2
Trying 192.168.23.2 ... Open

R2#who
Line         User    Host(s)     Idle       Location
0 con 0               idle     00:00:14
* 98 vty 0            idle     00:00:00    192.168.23.3

Interface    User        Mode         Idle     Peer Address 

R2#exit

[Connection to 192.168.23.2 closed by foreign host]
R1#telnet 192.168.34.4
Trying 192.168.34.4 ... Open

R4#who
Line         User    Host(s)     Idle       Location
0 con 0               idle     00:00:10
* 98 vty 0            idle     00:00:00   192.168.34.3

Interface    User        Mode         Idle     Peer Address 
MANUAL NAT GENERALIZATION

But what if the user wanted to live by a maxim and avoid unnecessary thinking? Can Manual NAT still be utilized while adhering to the static before dynamic generalization? The answer is yes; as long as a decision is taken to always place the dynamic NAT entries in Section 3 instead of Section 1.

There is a caveat here as well. Entries in Section 3, just like Section 1 do not order themselves automatically. This section should be treated just like Section 1 and the entries should be configured using a logic similar to ACL logic.
USING MANUAL DYNAMIC NAT IN SECTION 3

This is accomplished using just one keyword, after-auto, over the Manual NAT configuration already discussed above.

On an ASA where a current rule resides in Section 3, like this lab ASA, it is imperative to delete the current rules and reconfigure them with the after-auto keyword. Otherwise the old command never gets over written and the after-auto command will not be shown in the configuration at all.
ASA Configuration

ASA1(config)# no nat (inside,outside) source dynamic obj_192.168.13.0 interface
ASA1(config)# no nat (inside,dmz1) source dynamic obj_192.168.13.0 interface
ASA1(config)# nat (inside,outside) after-auto source dynamic obj_192.168.13.0 interface
ASA1(config)# nat (inside,dmz1) after-auto source dynamic obj_192.168.13.0 interface
The results are obvious in both the configuration and operational verification:

Verification

ASA1(config)# sho run nat
!
object network obj_192.168.13.0_outside
 nat (inside,outside) dynamic interface
object network obj_192.168.13.0_dmz1
 nat (inside,dmz1) dynamic interface
!
nat (inside,outside) after-auto source dynamic obj_192.168.13.0 interface
nat (inside,dmz1) after-auto source dynamic obj_192.168.13.0 interface

ASA1(config)# sho nat detail 

Auto NAT Policies (Section 2)
1 (inside) to (dmz1) source dynamic obj_192.168.13.0_dmz1 interface  
    translate_hits = 0, untranslate_hits = 0
    Source - Origin: 192.168.13.0/24, Translated: 192.168.34.3/24
2 (inside) to (outside) source dynamic obj_192.168.13.0_outside interface  
    translate_hits = 0, untranslate_hits = 0
    Source - Origin: 192.168.13.0/24, Translated: 192.168.23.3/24

Manual NAT Policies (Section 3)
1 (inside) to (outside) source dynamic obj_192.168.13.0 interface  
    translate_hits = 0, untranslate_hits = 0
    Source - Origin: 192.168.13.0/24, Translated: 192.168.23.3/24
2 (inside) to (dmz1) source dynamic obj_192.168.13.0 interface  
    translate_hits = 0, untranslate_hits = 0
    Source - Origin: 192.168.13.0/24, Translated: 192.168.34.3/24
Looking at the two outputs above, the problem should be obvious. If the intention was to NAT the packets using Manual NAT, then this configuration is deemed a failure. The packet tracer output illustrates this further:

Packet Tracer Verification
ASA1# packet-tracer input inside tcp 192.168.13.1 10000 192.168.23.2 23 

Phase: 1
Type: ACCESS-LIST
Subtype: 
Result: ALLOW
Config:
Implicit Rule
Additional Information:
MAC Access list

Phase: 2
Type: ROUTE-LOOKUP
Subtype: input
Result: ALLOW
Config:
Additional Information:
in   192.168.23.0    255.255.255.0   outside

Phase: 3
Type: IP-OPTIONS
Subtype: 
Result: ALLOW
Config:
Additional Information:

Phase: 4      
Type: NAT
Subtype: 
Result: ALLOW
Config:
object network obj_192.168.13.0_outside
 nat (inside,outside) dynamic interface
Additional Information:
Dynamic translate 192.168.13.1/10000 to 192.168.23.3/30999

Phase: 5
Type: IP-OPTIONS
Subtype: 
Result: ALLOW
Config:
Additional Information:

Phase: 6
Type: FLOW-CREATION
Subtype: 
Result: ALLOW
Config:
Additional Information:
New flow created with id 1, packet dispatched to next module
              
Result:
input-interface: inside
input-status: up
input-line-status: up
output-interface: outside
output-status: up
output-line-status: up
Action: allow
Caveat: Even though the ASA allows for the configuration of identical unmapped blocks (192.168.13/24) in Sections 1/3 and Section 2, during operation, the rule that takes precedence is the one that is used for the actual translation.
This does not cause trouble in the above scenario as all of the configured rules are performing the same translation. In the case where the rules in Section 3 were using a different mapped IP, however, the configuration would be deemed as misconfigured.

Results (Just for completeness)
R1#telnet 192.168.23.2
Trying 192.168.23.2 ... Open

R2#who
Line         User    Host(s)     Idle       Location
0 con 0              idle      00:05:15
* 98 vty 0           idle      00:00:00   192.168.23.3

Interface    User        Mode         Idle     Peer Address 

R2#exit

[Connection to 192.168.23.2 closed by foreign host]
R1#telnet 192.168.34.4
Trying 192.168.34.4 ... Open

R4#who
Line         User    Host(s)     Idle       Location
0 con 0              idle      00:04:34
* 98 vty 0           idle      00:00:00   192.168.34.3

Interface    User        Mode         Idle     Peer Address 
Dynamic PAT to a Non-ASA IP

This scenario is almost exactly the same as the previous one. For this reason, the packet tracer portion of the verification is skipped.

Using Network Object NAT

Once again, a separate object has to be created for each external interface for reasons discussed in the previous section. Other than that, the mapped IP address is stated in place of the interface keyword.

An object that contains the mapped IP as a host statement can also be used. Using just a mapped IP inside the network object makes for slightly less configuration and subjectively, a little more readability.

Instead of a subnet statement, a range statement is used in this example for demonstration purposes.
ASA Configuration

ASA1(config)#object network obj_192.168.13.0-13.50
ASA1(config-network-object)# range 192.168.13.1 192.168.13.50
ASA1(config-network-object)# nat (inside,any) dynamic 192.168.33.3
Since there is no restriction placed on the external interface now, the use of the any keyword is shown. This configuration will translate packets going out of either the Outside or DMZ interfaces to 192.168.33.3.

Verification

ASA1# sho run nat
!
----SNIP----
object network obj_192.168.13.0-13.50
 nat (inside,any) dynamic 192.168.33.3
!

ASA1# sho nat detail 

Auto NAT Policies (Section 2)
1 (inside) to (any) source dynamic obj_192.168.13.0-13.50 192.168.33.3  
    translate_hits = 0, untranslate_hits = 0
    Source - Origin: 192.168.13.1-192.168.13.50, Translated: 192.168.33.3/32
2 (inside) to (dmz1) source dynamic obj_192.168.13.0_dmz1 interface  
    translate_hits = 2, untranslate_hits = 0
    Source - Origin: 192.168.13.0/24, Translated: 192.168.34.3/24
3 (inside) to (outside) source dynamic obj_192.168.13.0_outside interface  
    translate_hits = 3, untranslate_hits = 0
    Source - Origin: 192.168.13.0/24, Translated: 192.168.23.3/24

Manual NAT Policies (Section 3)
----SNIP----
One thing that should be noted here is that the newest object has floated its way to the top of Section 2. The reason for this is that the IP block inside this object contains 50 addresses while each of the other blocks contains 254 IPs.
Caveat: For Auto NAT or NON, the order displayed in show run nat is different than the order shown in show nat. While show run nat shows the statements in the order of configuration, show nat shows the actual order of how the packets are matched against the statements. This is different than Section 1 and Section 3 where the orders are consistent between the two commands.
Result
R1#telnet 192.168.23.2
Trying 192.168.23.2 ... Open

R2#who
Line         User    Host(s)     Idle       Location
0 con 0               idle     00:00:32
* 98 vty 0            idle     00:00:00   192.168.33.3

Interface    User        Mode         Idle     Peer Address 

R2#exit

[Connection to 192.168.23.2 closed by foreign host]
R1#telnet 192.168.34.4
Trying 192.168.34.4 ... Open

R4#who
Line         User    Host(s)     Idle       Location
0 con 0               idle     00:00:30
98 vty 0              idle     01:42:35    192.168.34.3
* 99 vty 1            idle     00:00:00    192.168.33.3

Interface    User        Mode         Idle     Peer Address 
Using Manual NAT

With Manual NAT, there is no option of using the host IP address without an object for this scenario. Therefore, an object must be created for the mapped IP before the NAT can be configured.

As discussed in the first blog post of the series, the section where the statement will be placed is entirely up to the administrator and depends on many factors including current NAT configuration on the ASA and the logic used to match packets.

As an example, if the goal was to use the same range as used in the NON example above but translate those addresses to a different IP, there are two considerations. If one chose to delete the NON entry (as would be the norm in production networks), then the Manual NAT statement can be placed in either section with impunity. If, however, one were asked not to delete the NON entry (a typical CCIE lab scenario), then the only option would be to place the statement in Section 1. One can derive the reasoning by reading the discussion so far in this series.

Configuration

ASA1(config)# object network obj_192.168.33.33
ASA1(config-network-object)# host 192.168.33.33           
ASA1(config-network-object)# exit
ASA1(config)# nat (inside,any) source dynamic obj_192.168.13.0-13.50 
obj_192.168.33.33
Without the keyword after-auto, this statement should have been placed in Section 1, thus getting precedence over the existing NON statement.

Verification

ASA1(config)# sho run nat
nat (inside,any) source dynamic obj_192.168.13.0-13.50 obj_192.168.33.33
!
object network obj_192.168.13.0_outside
 nat (inside,outside) dynamic interface
object network obj_192.168.13.0_dmz1
 nat (inside,dmz1) dynamic interface
object network obj_192.168.13.0-13.50
 nat (inside,any) dynamic 192.168.33.3
!
nat (inside,outside) after-auto source dynamic obj_192.168.13.0 interface
nat (inside,dmz1) after-auto source dynamic obj_192.168.13.0 interface
ASA1(config)# 
ASA1(config)# sho nat
Manual NAT Policies (Section 1)
1 (inside) to (any) source dynamic obj_192.168.13.0-13.50 obj_192.168.33.33  
    translate_hits = 0, untranslate_hits = 0

Auto NAT Policies (Section 2)
1 (inside) to (any) source dynamic obj_192.168.13.0-13.50 192.168.33.3  
    translate_hits = 2, untranslate_hits = 0
2 (inside) to (dmz1) source dynamic obj_192.168.13.0_dmz1 interface  
    translate_hits = 0, untranslate_hits = 0
3 (inside) to (outside) source dynamic obj_192.168.13.0_outside interface  
    translate_hits = 0, untranslate_hits = 0

Manual NAT Policies (Section 3)
1 (inside) to (outside) source dynamic obj_192.168.13.0 interface  
    translate_hits = 0, untranslate_hits = 0
2 (inside) to (dmz1) source dynamic obj_192.168.13.0 interface  
    translate_hits = 0, untranslate_hits = 0
ASA1(config)# 
Packet tracer can again be utilized to see which statement will handle the translation. For brevity, that output is skipped and instead the telnet verification method is shown. Simply put, if R2 and R3 see R1’s IP as 192.168.33.33 and not 192.168.33.3, then it is the Manual NAT statement that is translating the traffic.

Results
R1#telnet 192.168.23.2
Trying 192.168.23.2 ... Open

R2#who
Line         User    Host(s)     Idle       Location
0 con 0               idle     00:25:22
* 98 vty 0            idle     00:00:00   192.168.33.3

Interface    User        Mode         Idle     Peer Address 

R2#
R2#exit

[Connection to 192.168.23.2 closed by foreign host]
R1#telnet 192.168.34.4
Trying 192.168.34.4 ... Open

R4#who
Line         User    Host(s)     Idle       Location
0 con 0               idle     00:26:07
* 98 vty 0            idle     01:42:35   192.168.33.3

Interface    User        Mode         Idle     Peer Address 

