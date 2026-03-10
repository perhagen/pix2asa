Dynamic PAT Cont. with Pools, Flat, Round-Robin and Extended PAT
​
 Summarize
​
04 // 30 // 15
NetCraftsmen®

Edited by Marilyn Outerbridge

This is the third blog post of a series. For the series, please click here. All of the configuration scenarios continue from the previous blog post in the series.
Table of Contents

Dynamic PAT Continue
ASA Mapped Port Selection
Dynamic PAT to a Pool of IP Addresses
Using Network Object NAT (NON)
Port Collisions
Scenario setup
Default ASA PAT Behavior for Port-Collision
Verification
Implications of Default Behavior
Changing the Default Behavior
Flat
Implication of Using Flat Keyword
Flat include-reserve
Round-Robin Keyword
Mixing Knobs – Example Round-Robin with Flat
Extended Keyword
The Setup and Demonstration
Using Manual NAT
The NAT examples in the article are taken from the following topology:

ASA Nat

Figure 2-1: ASA NAT Topology

1. Dynamic PAT Continued

1.1 ASA Mapped Port Selection

Before continuing the discussion of further dynamic NAT scenarios, it is important to understand how ASA selects the mapped port for any translation. The process is described in the Cisco documentation as follows:

If available, the real source port number is used for the mapped port. However, if the real port is not available, by default the mapped ports are chosen from the same range of ports as the real port number: 0 to 511, 512 to 1023, and 1024 to 65535. Therefore, ports below 1024 have only a small PAT pool that can be used. (8.4(3) and later, not including 8.5(1) or 8.6(1)) If you have a lot of traffic that uses the lower port ranges, you can now specify a flat range of ports to be used instead of the three unequal-sized tiers: either 1024 to 65535, or 1 to 65535.

The rest of the blog post will explain this behavior in detail, with examples. Put very succinctly, when a port translation occurs, the ASA will always try to provide a mapped source port that is identical to the real source port, provided that the mapped port is not already in use by another translation.

With the current configuration on the ASA (as of the last blog post in the series) this behavior can be seen in the outputs below. To produce these outputs, 6 simultaneous telnet connections were initiated from R1:

3 towards R2
3 towards R4
Verification on ASA

ASA1(config)# sho xlate
 6 in use, 7 most used
 Flags: D - DNS, i - dynamic, r - portmap, s - static, I - identity, T - twice
        e - extended
 TCP PAT from inside:192.168.13.1/29853 to any:192.168.33.33/29853 flags ri idle 0:02:09 timeout 0:00:30
 TCP PAT from inside:192.168.13.1/50337 to any:192.168.33.33/50337 flags ri idle 0:02:12 timeout 0:00:30
 TCP PAT from inside:192.168.13.1/63128 to any:192.168.33.33/63128 flags ri idle 0:02:15 timeout 0:00:30
 TCP PAT from inside:192.168.13.1/17969 to any:192.168.33.33/17969 flags ri idle 0:02:22 timeout 0:00:30
 TCP PAT from inside:192.168.13.1/40431 to any:192.168.33.33/40431 flags ri idle 0:02:25 timeout 0:00:30
 TCP PAT from inside:192.168.13.1/43791 to any:192.168.33.33/43791 flags ri idle 0:02:29 timeout 0:00:30
ASA1(config)#
 
Verification on Source
 
R1#sho tcp brief
 TCB       Local Address           Foreign Address      (state)
 03016278  192.168.13.1.29853      192.168.34.4.23       ESTAB
 03012F10  192.168.13.1.43791      192.168.23.2.23       ESTAB
 03013958  192.168.13.1.40431      192.168.23.2.23       ESTAB
 03014DE8  192.168.13.1.63128      192.168.34.4.23       ESTAB
 030143A0  192.168.13.1.17969      192.168.23.2.23       ESTAB
 03015830  192.168.13.1.50337      192.168.34.4.23       ESTAB
R1#
 
Verification on Destinations
R2#show tcp brief
 TCB       Local Address           Foreign Address      (state)
 03DFED50  192.168.23.2.23         192.168.33.33.43791   ESTAB
 03E16F48  192.168.23.2.23         192.168.33.33.17969   ESTAB
 03DFF204  192.168.23.2.23         192.168.33.33.40431   ESTAB
R2#
 
R4#show tcp brief
 TCB       Local Address           Foreign Address      (state)
 063B32DC  192.168.34.4.23         192.168.33.33.50337   ESTAB
 063BCC8C  192.168.34.4.23         192.168.33.33.29853   ESTAB
 05289A80  192.168.34.4.23         192.168.33.33.63128   ESTAB
R4#
It is clear that the ASA is trying to preserve (and with such a small number of translations, succeeding in preserving) the port numbers across a translation.

With that idea as the backdrop, it is time to continue the discussion of the dynamic PAT types on the ASA. The reader will be introduced to all of the issues arising from this ASA behavior as well as the possible tweaks available in the ASA code to override some of the peculiar aspects of it.

Note: To keep the article short enough to still be called a blog post, all of these knobs/tweaks for the above behavior will be demonstrated in the first subsection of Dynamic PAT to a Pool of IP Addresses – i.e. Using Network Object NAT.

The concepts covered in that subsection translate directly to Manual NAT and therefore the demonstrations are deemed redundant and not covered in this blog post.
1.2 Dynamic PAT to a Pool of IP Addresses

These scenarios increase the number of mapped IP addresses from a single IP address to a pool of multiple IP addresses.

Just as before, there are two options (technically three with Manual NAT After-Auto) available to the ASA administrator.

1.2.1 Using Network Object NAT (NON)

For this scenario, the ASA is translating the inside IP block, 192.168.13/24 to the following pools:

168.33.60 – 192.168.33.65 on interface outside
168.33.50 – 192.168.33.55 on interface dmz1
Since the existing NAT statement in Section 1 would override any statements configured in Section 2, it was set to inactive for this part of the demonstration. Additionally, the NAT statement under the obj_192.168.13.0-13.50 was deleted for the exact same reason.

ASA1(config)#nat (inside,any) source dynamic obj_192.168.13.0-13.50 obj_192.168.33.33 inactive
!
ASA1(config)# object network obj_192.168.13.0-13.50
ASA1(config-network-object)# no  nat (inside,any) dynamic 192.168.33.3
Two new objects are created to hold the new IP address pools.

ASA1(config)# object network obj_192.168.33.50-55
ASA1(config-network-object)# range 192.168.33.50 192.168.33.55
ASA1(config-network-object)# object network obj_192.168.33.60-65
ASA1(config-network-object)# range 192.168.33.60 192.168.33.65
Finally, the two existing objects containing the 192.168.13/24 range (one each for outside and dmz1 interfaces) are configured with NAT statements referencing the appropriate IP pools:

Configuration
 
ASA1#show run nat
<SNIP>
 !
object network obj_192.168.13.0_outside
 nat (inside,dmz1) dynamic pat-pool obj_192.168.33.60-65
object network obj_192.168.13.0_dmz1
 nat (inside,outside) dynamic pat-pool obj_192.168.33.50-55
!
<SNIP>
The same 6 simultaneous connections, as shown earlier in this blog post, are initiated from R1 to R2 and R4 just for a quick verification.

Verification on Source

R1#show tcp brief
TCB       Local Address           Foreign Address      (state)
03016278  192.168.13.1.64038      192.168.34.4.23       ESTAB
030143A0  192.168.13.1.64773      192.168.23.2.23       ESTAB
03015830  192.168.13.1.28989      192.168.34.4.23       ESTAB
03014DE8  192.168.13.1.27652      192.168.34.4.23       ESTAB
03012F10  192.168.13.1.17387      192.168.23.2.23       ESTAB
03013958  192.168.13.1.39312      192.168.23.2.23       ESTAB
R1#

Verification on Destinations

R2#show tcp brief
TCB       Local Address           Foreign Address      (state)
03DFED50  192.168.23.2.23         192.168.33.50.39312   ESTAB
03E16A94  192.168.23.2.23         192.168.33.50.64773   ESTAB
03DFE89C  192.168.23.2.23         192.168.33.50.17387   ESTAB
R2#
!
R4#show tcp brief
TCB       Local Address           Foreign Address      (state)
063B3734  192.168.34.4.23         192.168.33.60.64038   ESTAB
063BC834  192.168.34.4.23         192.168.33.60.28989   ESTAB
05288DC0  192.168.34.4.23         192.168.33.60.27652   ESTAB
R4#
1.2.1.1 Port Collisions

In a production network with a significant number of hosts generating a decent amount of connections, there will always be “port collisions” — i.e. two or more connections with identical real ports requiring translation simultaneously.

The next set of scenarios explores the various ASA PAT behaviors in these situations.

1.2.1.2 Scenario setup:

To demonstrate the ASA PAT behavior clearly with a minimal amount of connections, the DMZ interface is not utilized for these scenarios.

All the traffic is generated from devices on the Inside interface to devices on the outside interface.
The following traffic is artificially generated:

Protocol	Source IP	Source Port
UDP	192.168.13.5	100
UDP	192.168.13.5	200
UDP	192.168.13.5	600
UDP	192.168.13.5	700
UDP	192.168.13.5	10000
UDP	192.168.13.5	20000
UDP	192.168.13.101	100
UDP	192.168.13.1	200
UDP	192.168.13.101	600
UDP	192.168.13.1	700
UDP	192.168.13.1	10000
UDP	192.168.13.1	20000
The destination IP and destination ports are irrelevant to the scenarios because each scenario demonstrates only source PAT translation.

The main point to note in the table above is that there will be one collision per port listed.
1.2.1.3 Default ASA PAT Behavior for Port-Collision

A specific portion of the first part of the Cisco statement on the ASA PAT behavior bears repeating here:

If available, the real source port number is used for the mapped port. However, if the real port is not available, by default the mapped ports are chosen from the same range of ports as the real port number: 0 to 511, 512 to 1023, and 1024 to 65535.

In other words, in case there is a conflict — a port collision — and an identical mapped port cannot be provided, the ASA, by default, will check which of the following ranges the real source port fits under:

0 – 511
512 – 1023
1024 – 65535
Once the correct range is determined, a substitute mapped port number will be chosen from the same range as the original port.

For example, suppose a new connection requiring source PAT has a source port of 401. If the mapped source port number 401 is already in use for another translation, it is obvious that the ASA cannot preserve the source port for the translation. To complete that translation, a mapped port number must be chosen. The ASA will next determine which of the three ranges include 401. With that data (0-511) the ASA will now proceed to choose a substitute mapped port number from the 0 – 511 range.

Similarly, if the real source port in the above scenario was 1001, the mapped port number would have been selected from the 512 – 1023 range.

One potential concern is that certain issues can arise if there are a large number of applications that are using ports from the well-known port number range (0-1023) as source ports.

The range here is small, consequently the chance of conflicts is high. Furthermore, in case of a conflict, there is a much smaller range of substitute ports.

This behavior can be changed as of 8.4(3) (with a couple of exceptions as noted in the excerpt from Cisco).

In fact, your humble author had to scramble to find an ASA with proper code to demonstrate the new knobs. (The previous blogs collected outputs from 8.4(2) ASA code).
Without further adieu, it is time to take a look at the realization of this behavior with real traffic.

For this demonstration, all the connections from the connection table were simultaneously launched and the ASA translated them. The xlate table output was collected for each connection.

To improve readability, the entire xlate table was divided into the three relevant ranges.

Range 0-511:

ASA1(config-network-object)# sho xlate
4 in use, 8 most used
Flags: D - DNS, i - dynamic, r - portmap, s - static, I - identity, T - twice
       e - extended
UDP PAT from inside:192.168.13.101/100 to outside:192.168.33.50/100 flags ri idle 0:00:06 timeout 0:00:30
UDP PAT from inside:192.168.13.5/200 to outside:192.168.33.50/29 flags ri idle 0:00:01 timeout 0:00:30
UDP PAT from inside:192.168.13.5/100 to outside:192.168.33.50/400 flags ri idle 0:00:04 timeout 0:00:30
UDP PAT from inside:192.168.13.1/200 to outside:192.168.33.50/200 flags ri idle 0:00:06 timeout 0:00:30
<SNIP>
The connections with the green highlights were processed by the ASA before the connections with red highlights. As a result, the two “green” connections were provided identical mapped source ports but the two “red” connections had to be provided with substitute mapped source ports. The substitutions are as follows:

100 -> 400
200 -> 29
These are random substitutions but the substitute mapped source ports are from the same range (0-511) as the original source ports.

Range 512 – 1023

ASA1(config)# sho xlate
8 in use, 8 most used
Flags: D - DNS, i - dynamic, r - portmap, s - static, I - identity, T - twice
       e - extended
UDP PAT from inside:192.168.13.101/600 to outside:192.168.33.50/600 flags ri idle 0:00:36 timeout 0:00:30
<SNIP>
UDP PAT from inside:192.168.13.5/700 to outside:192.168.33.50/1019 flags ri idle 0:00:05 timeout 0:00:30
UDP PAT from inside:192.168.13.5/600 to outside:192.168.33.50/550 flags ri idle 0:00:07 timeout 0:00:30
<SNIP>
UDP PAT from inside:192.168.13.1/700 to outside:192.168.33.50/700 flags ri idle 0:00:34 timeout 0:00:30
<SNIP>
Same concept as before applied under this range. This time the substitute mapped source ports are:

600 -> 550
700 -> 1019
Once again, it should be noted that the substitute mapped source ports were selected from the same range (512 – 1023) as the real source ports.

Range 1024 – 65535

ASA1(config)# sho xlate
12 in use, 12 most used
Flags: D - DNS, i - dynamic, r - portmap, s - static, I - identity, T - twice
       e - extended
<SNIP>
UDP PAT from inside:192.168.13.5/20000 to outside:192.168.33.50/42505 flags ri idle 0:00:09 timeout 0:00:30
UDP PAT from inside:192.168.13.5/10000 to outside:192.168.33.50/61356 flags ri idle 0:00:11 timeout 0:00:30
<SNIP>
UDP PAT from inside:192.168.13.1/20000 to outside:192.168.33.50/20000 flags ri idle 0:00:14 timeout 0:00:30
UDP PAT from inside:192.168.13.1/10000 to outside:192.168.33.50/10000 flags ri idle 0:00:16 timeout 0:00:30
<SNIP>
For the last set of connections, the substitute mapped source ports are:

10000 -> 61356
20000 -> 42505
Needless to say, the range (1024 – 65535) is again consistent between the real source ports and substitute mapped source ports.

1.2.1.3.1 Verification

The show nat pool command gives an excellent summary of the above behavior.

ASA1(config)# sho nat pool
UDP PAT pool outside:obj_192.168.33.50-55, address 192.168.33.50, range 1-511, allocated 4
UDP PAT pool outside:obj_192.168.33.50-55, address 192.168.33.50, range 512-1023, allocated 4
UDP PAT pool outside:obj_192.168.33.50-55, address 192.168.33.50, range 1024-65535, allocated 4
UDP PAT pool outside, address 192.168.23.3, range 1-511, allocated 0
UDP PAT pool outside, address 192.168.23.3, range 512-1023, allocated 0
UDP PAT pool outside, address 192.168.23.3, range 1024-65535, allocated 4
UDP PAT pool inside, address 192.168.13.3, range 1-511, allocated 0
UDP PAT pool inside, address 192.168.13.3, range 512-1023, allocated 0
UDP PAT pool inside, address 192.168.13.3, range 1024-65535, allocated 4
UDP PAT pool dmz1, address 192.168.34.3, range 1-511, allocated 0
UDP PAT pool dmz1, address 192.168.34.3, range 512-1023, allocated 0
UDP PAT pool dmz1, address 192.168.34.3, range 1024-65535, allocated 4
It is quite clearly seen that each of the connections fits into one of the three ranges. Furthermore, the command shows the utilization of each specific range. During troubleshooting of NAT issues, this command becomes essential as it would be a very good indicator of NAT pool exhaustion.

1.2.1.3.2 Implications of Default Behavior

It is important to consider the result of port exhaustion with this behavior. In short, if a particular range runs out of mapped ports, no more translations can take place for real source ports that fit under those ranges. The ASA will move to the next address in the pool, following the same criteria within the pool of ports and within those addresses.

Essentially, a port exhaustion problem could occur in environments where a significantly large number of applications use real source ports within the two smaller ranges. The chance of port exhaustion is higher by many orders for these applications because of the relatively small size of the two pools.

1.2.1.4 Changing the Default Behavior

As of ASA code 8.4(3), the ASA provides knobs that allow the administrator to change the default behavior just described. These knobs are:

Flat
Flat include-reserve
1.2.1.5 Flat

The flat keyword changes the default behavior by using only the ephemeral ports (1024 – 65535) for the selection of the mapped source ports. The major change here from the default behavior is that even the real source ports from the well-known range (0 – 1023) are translated to the mapped source ports in the ephemeral range.

Configuration

ASA1(config)# sho run nat
nat (inside,any) source dynamic obj_192.168.13.0-13.50 obj_192.168.33.33 inactive
!
object network obj_192.168.13.0_dmz1
 nat (inside,dmz1) dynamic pat-pool obj_192.168.33.60-65 flat
object network obj_192.168.13.0_outside
 nat (inside,outside) dynamic pat-pool obj_192.168.33.50-55 flat
!
nat (inside,outside) after-auto source dynamic obj_192.168.13.0 interface
nat (inside,dmz1) after-auto source dynamic obj_192.168.13.0 interface

Verification

ASA1(config)# sho xlate
12 in use, 12 most used
Flags: D - DNS, i - dynamic, r - portmap, s - static, I - identity, T - twice
       e - extended
UDP PAT from inside:192.168.13.101/600 to outside:192.168.33.50/21624 flags ri idle 0:00:03 timeout 0:00:30
UDP PAT from inside:192.168.13.101/100 to outside:192.168.33.50/63801 flags ri idle 0:00:05 timeout 0:00:30
UDP PAT from inside:192.168.13.5/200 to outside:192.168.33.50/54602 flags ri idle 0:00:00 timeout 0:00:30
UDP PAT from inside:192.168.13.5/100 to outside:192.168.33.50/22531 flags ri idle 0:00:03 timeout 0:00:30
UDP PAT from inside:192.168.13.5/700 to outside:192.168.33.50/50510 flags ri idle 0:00:03 timeout 0:00:30
UDP PAT from inside:192.168.13.5/600 to outside:192.168.33.50/27255 flags ri idle 0:00:05 timeout 0:00:30
UDP PAT from inside:192.168.13.5/20000 to outside:192.168.33.50/20000 flags ri idle 0:00:07 timeout 0:00:30
UDP PAT from inside:192.168.13.5/10000 to outside:192.168.33.50/10000 flags ri idle 0:00:08 timeout 0:00:30
UDP PAT from inside:192.168.13.1/700 to outside:192.168.33.50/45905 flags ri idle 0:00:02 timeout 0:00:30
UDP PAT from inside:192.168.13.1/20000 to outside:192.168.33.50/21780 flags ri idle 0:00:02 timeout 0:00:30
UDP PAT from inside:192.168.13.1/10000 to outside:192.168.33.50/42213 flags ri idle 0:00:03 timeout 0:00:30
UDP PAT from inside:192.168.13.1/200 to outside:192.168.33.50/4370 flags ri idle 0:00:05 timeout 0:00:30
There is a notable difference in these results versus the results seen in the scenario using default behavior.  In that instance, if there was no port conflict, all real source ports received identical mapped source ports. In this scenario, a real source port from the well-known range can never receive an identical mapped port. All real source ports from the well-known range will receive substitute mapped source ports from the ephemeral range regardless of port conflict. This can be seen in the output below.

100 -> 22531
100 -> 63801
200 -> 4370
200 -> 54602
600 -> 21624
600 -> 27255
700 -> 45905
700 -> 50510
This is essentially because the range of well-known ports is not even considered as a mapped source port option with this keyword.

1.2.1.5.1 Implication of Using Flat Keyword

The biggest implication here is that even though port exhaustion rate is the same for all ports, there needs to be a realization that there is absolutely zero chance for applications using well-known source ports to maintain their source ports across the NAT.

Caveat: The show nat pool command for this scenario is confusing as well as misleading. It shows two separate ranges for the pool using the flat keyword. The ranges show up as 1 – 1024 and 1024 – 65535. In actuality, the ASA never uses the first range for a statement configured with the flat keyword.
ASA1(config)# show nat pool
UDP PAT pool outside:obj_192.168.33.50-55, address 192.168.33.50, range 1-1024, allocated 0
UDP PAT pool outside:obj_192.168.33.50-55, address 192.168.33.50, range 1024-65535, allocated 12
UDP PAT pool outside, address 192.168.23.3, range 1-511, allocated 0
UDP PAT pool outside, address 192.168.23.3, range 512-1023, allocated 0
UDP PAT pool outside, address 192.168.23.3, range 1024-65535, allocated 4
UDP PAT pool inside, address 192.168.13.3, range 1-511, allocated 0
UDP PAT pool inside, address 192.168.13.3, range 512-1023, allocated 0
UDP PAT pool inside, address 192.168.13.3, range 1024-65535, allocated 4
UDP PAT pool dmz1, address 192.168.34.3, range 1-511, allocated 0
UDP PAT pool dmz1, address 192.168.34.3, range 512-1023, allocated 0
UDP PAT pool dmz1, address 192.168.34.3, range 1024-65535, allocated 4
Above is the output of show nat pool collected immediately after the show xlate output collected above it. Obviously the 1 – 1024 range is not being utilized. All of the translations are using addresses from the 1024 – 65535 range.

1.2.1.6 Flat include-reserve

The include-reserve sub-knob of the flat keyword tweaks the above behavior further. This is probably the most straightforward out of all the behaviors discussed. Quite simply, the available range now includes all possible ports, i.e. 1 – 65535 (0 is somehow still not made available, even theoretically). This makes the translations very predictable and no particular port or port range is any more susceptible to exhaustion than any other port or port range.

ASA1(config)# sho run nat
nat (inside,any) source dynamic obj_192.168.13.0-13.50 obj_192.168.33.33 inactive
!
object network obj_192.168.13.0_dmz1
 nat (inside,dmz1) dynamic pat-pool obj_192.168.33.60-65 flat include-reserve
object network obj_192.168.13.0_outside
 nat (inside,outside) dynamic pat-pool obj_192.168.33.50-55 flat include-reserve
!
nat (inside,outside) after-auto source dynamic obj_192.168.13.0 interface
nat (inside,dmz1) after-auto source dynamic obj_192.168.13.0 interface
Verification

ASA1(config)# sho xlate
12 in use, 12 most used
Flags: D - DNS, i - dynamic, r - portmap, s - static, I - identity, T - twice
       e - extended
UDP PAT from inside:192.168.13.101/600 to outside:192.168.33.50/53839 flags ri idle 0:00:07 timeout 0:00:30
UDP PAT from inside:192.168.13.101/100 to outside:192.168.33.50/100 flags ri idle 0:00:08 timeout 0:00:30
UDP PAT from inside:192.168.13.5/20000 to outside:192.168.33.50/41868 flags ri idle 0:00:00 timeout 0:00:30
UDP PAT from inside:192.168.13.5/10000 to outside:192.168.33.50/50523 flags ri idle 0:00:02 timeout 0:00:30
UDP PAT from inside:192.168.13.5/200 to outside:192.168.33.50/8454 flags ri idle 0:00:03 timeout 0:00:30
UDP PAT from inside:192.168.13.5/100 to outside:192.168.33.50/32624 flags ri idle 0:00:06 timeout 0:00:30
UDP PAT from inside:192.168.13.5/700 to outside:192.168.33.50/700 flags ri idle 0:00:06 timeout 0:00:30
UDP PAT from inside:192.168.13.5/600 to outside:192.168.33.50/600 flags ri idle 0:00:08 timeout 0:00:30
UDP PAT from inside:192.168.13.1/700 to outside:192.168.33.50/17533 flags ri idle 0:00:05 timeout 0:00:30
UDP PAT from inside:192.168.13.1/20000 to outside:192.168.33.50/20000 flags ri idle 0:00:05 timeout 0:00:30
UDP PAT from inside:192.168.13.1/10000 to outside:192.168.33.50/10000 flags ri idle 0:00:07 timeout 0:00:30
UDP PAT from inside:192.168.13.1/200 to outside:192.168.33.50/200 flags ri idle 0:00:08 timeout 0:00:30
Finally, an output of the show nat pool showing a single range of pools being used for mapped source ports.

ASA1(config)# sho nat pool
UDP PAT pool outside:obj_192.168.33.50-55, address 192.168.33.50, range 1-65535, allocated 12
UDP PAT pool outside, address 192.168.23.3, range 1-511, allocated 0
UDP PAT pool outside, address 192.168.23.3, range 512-1023, allocated 0
UDP PAT pool outside, address 192.168.23.3, range 1024-65535, allocated 4
UDP PAT pool inside, address 192.168.13.3, range 1-511, allocated 0
UDP PAT pool inside, address 192.168.13.3, range 512-1023, allocated 0
UDP PAT pool inside, address 192.168.13.3, range 1024-65535, allocated 4
UDP PAT pool dmz1, address 192.168.34.3, range 1-511, allocated 0
UDP PAT pool dmz1, address 192.168.34.3, range 512-1023, allocated 0
UDP PAT pool dmz1, address 192.168.34.3, range 1024-65535, allocated 4
1.2.1.7 Round-Robin Keyword

In all of the previous examples, with or without the extra knobs, the ASA code always ensured that all ports of an address within a pool were exhausted before it started to utilize the next address in the pool.

With the round-robin knob, each new unique address is assigned the next IP address in the pool. The pool is treated as a circular data structure so after the last IP of the pool is assigned to a real address, the next unique real address is assigned the first IP in the pool. This means there is a better distribution of real IPs to the mapped IPs and a much better chance that the real ports will be assigned identical mapped ports after translation.

Configuration

ASA1(config)# sho run nat
nat (inside,any) source dynamic obj_192.168.13.0-13.50 obj_192.168.33.33 inactive
!
object network obj_192.168.13.0_dmz1
 nat (inside,dmz1) dynamic pat-pool obj_192.168.33.60-65 round-robin
object network obj_192.168.13.0_outside
 nat (inside,outside) dynamic pat-pool obj_192.168.33.50-55 round-robin
!
nat (inside,outside) after-auto source dynamic obj_192.168.13.0 interface
nat (inside,dmz1) after-auto source dynamic obj_192.168.13.0 interface
For the verification of this configuration, there are two outputs used in this post: a single output of the show xlate and then the same output broken into the different real IP/mapped IP pairs.

Verification

ASA1(config)# sho xlate
12 in use, 13 most used
Flags: D - DNS, i - dynamic, r - portmap, s - static, I - identity, T - twice
       e - extended
UDP PAT from inside:192.168.13.101/600 to outside:192.168.33.50/600 flags ri idle 0:00:14 timeout 0:00:30
UDP PAT from inside:192.168.13.101/100 to outside:192.168.33.50/100 flags ri idle 0:00:16 timeout 0:00:30
UDP PAT from inside:192.168.13.5/10000 to outside:192.168.33.55/10000 flags ri idle 0:00:09 timeout 0:00:30
UDP PAT from inside:192.168.13.5/200 to outside:192.168.33.55/200 flags ri idle 0:00:10 timeout 0:00:30
UDP PAT from inside:192.168.13.5/100 to outside:192.168.33.55/100 flags ri idle 0:00:13 timeout 0:00:30
UDP PAT from inside:192.168.13.5/700 to outside:192.168.33.55/700 flags ri idle 0:00:14 timeout 0:00:30
UDP PAT from inside:192.168.13.5/600 to outside:192.168.33.55/600 flags ri idle 0:00:15 timeout 0:00:30
UDP PAT from inside:192.168.13.5/20000 to outside:192.168.33.55/20000 flags ri idle 0:00:17 timeout 0:00:30
UDP PAT from inside:192.168.13.1/700 to outside:192.168.33.51/700 flags ri idle 0:00:12 timeout 0:00:30
UDP PAT from inside:192.168.13.1/20000 to outside:192.168.33.51/20000 flags ri idle 0:00:12 timeout 0:00:30
UDP PAT from inside:192.168.13.1/10000 to outside:192.168.33.51/10000 flags ri idle 0:00:14 timeout 0:00:30
UDP PAT from inside:192.168.13.1/200 to outside:192.168.33.51/200 flags ri idle 0:00:16 timeout 0:00:30
Below is that same output but this time broken down by real IPs. Per the real source IP, real source port table shown earlier, there are three unique source IPs.

ASA1(config)# show xlate local 192.168.13.1
12 in use, 13 most used
Flags: D - DNS, i - dynamic, r - portmap, s - static, I - identity, T - twice
       e - extended
UDP PAT from inside:192.168.13.1/700 to outside:192.168.33.51/700 flags ri idle 0:01:25 timeout 0:00:30
UDP PAT from inside:192.168.13.1/20000 to outside:192.168.33.51/20000 flags ri idle 0:01:25 timeout 0:00:30
UDP PAT from inside:192.168.13.1/10000 to outside:192.168.33.51/10000 flags ri idle 0:01:26 timeout 0:00:30
UDP PAT from inside:192.168.13.1/200 to outside:192.168.33.51/200 flags ri idle 0:01:28 timeout 0:00:30

ASA1(config)# show xlate local 192.168.13.5
12 in use, 13 most used
Flags: D - DNS, i - dynamic, r - portmap, s - static, I - identity, T - twice
       e - extended
UDP PAT from inside:192.168.13.5/10000 to outside:192.168.33.55/10000 flags ri idle 0:02:03 timeout 0:00:30
UDP PAT from inside:192.168.13.5/200 to outside:192.168.33.55/200 flags ri idle 0:02:05 timeout 0:00:30
UDP PAT from inside:192.168.13.5/100 to outside:192.168.33.55/100 flags ri idle 0:02:08 timeout 0:00:30
UDP PAT from inside:192.168.13.5/700 to outside:192.168.33.55/700 flags ri idle 0:02:08 timeout 0:00:30
UDP PAT from inside:192.168.13.5/600 to outside:192.168.33.55/600 flags ri idle 0:02:10 timeout 0:00:30
UDP PAT from inside:192.168.13.5/20000 to outside:192.168.33.55/20000 flags ri idle 0:02:12 timeout 0:00:30

ASA1(config)# sho xlate local 192.168.13.101
12 in use, 13 most used
Flags: D - DNS, i - dynamic, r - portmap, s - static, I - identity, T - twice
       e - extended
UDP PAT from inside:192.168.13.101/600 to outside:192.168.33.50/600 flags ri idle 0:03:05 timeout 0:00:30
UDP PAT from inside:192.168.13.101/100 to outside:192.168.33.50/100 flags ri idle 0:03:07 timeout 0:00:30
It is clear that each of the real IPs in the scenario were each assigned a unique mapped IP:

192.168.13.1 – 192.168.33.51
192.168.13.5 – 192.168.33.55
192.168.13.101 – 192.168.33.50
Furthermore, this is the first time in this blog post where all of the real source ports were preserved across the translation.

The show nat pool verification further shows that each of the IPs in the pool were using the default behavior when it came to real source port to mapped source port preservation.

ASA1(config)# sho nat pool
UDP PAT pool outside:obj_192.168.33.50-55, address 192.168.33.55, range 1-511, allocated 2
UDP PAT pool outside:obj_192.168.33.50-55, address 192.168.33.55, range 512-1023, allocated 2
UDP PAT pool outside:obj_192.168.33.50-55, address 192.168.33.55, range 1024-65535, allocated 2
UDP PAT pool outside:obj_192.168.33.50-55, address 192.168.33.50, range 1-511, allocated 1
UDP PAT pool outside:obj_192.168.33.50-55, address 192.168.33.50, range 512-1023, allocated 1
UDP PAT pool outside:obj_192.168.33.50-55, address 192.168.33.50, range 1024-65535, allocated 0
UDP PAT pool outside, address 192.168.23.3, range 1-511, allocated 0
UDP PAT pool outside, address 192.168.23.3, range 512-1023, allocated 0
UDP PAT pool outside, address 192.168.23.3, range 1024-65535, allocated 4
UDP PAT pool outside:obj_192.168.33.50-55, address 192.168.33.51, range 1-511, allocated 1
UDP PAT pool outside:obj_192.168.33.50-55, address 192.168.33.51, range 512-1023, allocated 1
UDP PAT pool outside:obj_192.168.33.50-55, address 192.168.33.51, range 1024-65535, allocated 2
UDP PAT pool inside, address 192.168.13.3, range 1-511, allocated 0
UDP PAT pool inside, address 192.168.13.3, range 512-1023, allocated 0
UDP PAT pool inside, address 192.168.13.3, range 1024-65535, allocated 4
UDP PAT pool dmz1, address 192.168.34.3, range 1-511, allocated 0
UDP PAT pool dmz1, address 192.168.34.3, range 512-1023, allocated 0
UDP PAT pool dmz1, address 192.168.34.3, range 1024-65535, allocated 4
1.2.1.8 Mixing Knobs – Example Round-Robin with Flat

The knobs can be mixed in a variety of combinations. In the following example, the round-robin knob was used in tandem with the flat knob to produce a mapped source port range of 1024 – 65535. The reader is again reminded to ignore the 1 – 1024 range based on the caveat stated in the flat keyword section.

ASA1(config-network-object)# show run nat
nat (inside,any) source dynamic obj_192.168.13.0-13.50 obj_192.168.33.33 inactive
!
object network obj_192.168.13.0_dmz1
 nat (inside,dmz1) dynamic pat-pool obj_192.168.33.60-65 flat round-robin
object network obj_192.168.13.0_outside
 nat (inside,outside) dynamic pat-pool obj_192.168.33.50-55 flat round-robin
!
nat (inside,outside) after-auto source dynamic obj_192.168.13.0 interface
nat (inside,dmz1) after-auto source dynamic obj_192.168.13.0 interface
Verification

ASA1# sho xlate local 192.168.13.1
12 in use, 13 most used
Flags: D - DNS, i - dynamic, r - portmap, s - static, I - identity, T - twice
       e - extended
UDP PAT from inside:192.168.13.1/700 to outside:192.168.33.55/15489 flags ri idle 0:00:25 timeout 0:00:30
UDP PAT from inside:192.168.13.1/20000 to outside:192.168.33.55/20000 flags ri idle 0:00:25 timeout 0:00:30
UDP PAT from inside:192.168.13.1/10000 to outside:192.168.33.55/10000 flags ri idle 0:00:26 timeout 0:00:30
UDP PAT from inside:192.168.13.1/200 to outside:192.168.33.55/37224 flags ri idle 0:00:28 timeout 0:00:30

ASA1# sho xlate local 192.168.13.5
12 in use, 13 most used
Flags: D - DNS, i - dynamic, r - portmap, s - static, I - identity, T - twice
       e - extended
UDP PAT from inside:192.168.13.5/10000 to outside:192.168.33.53/10000 flags ri idle 0:00:27 timeout 0:00:30
UDP PAT from inside:192.168.13.5/200 to outside:192.168.33.53/34490 flags ri idle 0:00:29 timeout 0:00:30
UDP PAT from inside:192.168.13.5/100 to outside:192.168.33.53/62724 flags ri idle 0:00:32 timeout 0:00:30
UDP PAT from inside:192.168.13.5/700 to outside:192.168.33.53/56755 flags ri idle 0:00:32 timeout 0:00:30
UDP PAT from inside:192.168.13.5/600 to outside:192.168.33.53/39701 flags ri idle 0:00:33 timeout 0:00:30
UDP PAT from inside:192.168.13.5/20000 to outside:192.168.33.53/20000 flags ri idle 0:00:35 timeout 0:00:30

ASA1# sho xlate local 192.168.13.101
12 in use, 13 most used
Flags: D - DNS, i - dynamic, r - portmap, s - static, I - identity, T - twice
       e - extended
UDP PAT from inside:192.168.13.101/600 to outside:192.168.33.54/20414 flags ri idle 0:00:36 timeout 0:00:30
UDP PAT from inside:192.168.13.101/100 to outside:192.168.33.54/60711 flags ri idle 0:00:37 timeout 0:00:30

ASA1# sho nat pool
UDP PAT pool outside:obj_192.168.33.50-55, address 192.168.33.55, range 1-1024, allocated 0
UDP PAT pool outside:obj_192.168.33.50-55, address 192.168.33.55, range 1024-65535, allocated 4
UDP PAT pool outside:obj_192.168.33.50-55, address 192.168.33.50, range 1-1024, allocated 0
UDP PAT pool outside:obj_192.168.33.50-55, address 192.168.33.50, range 1024-65535, allocated 0
UDP PAT pool outside:obj_192.168.33.50-55, address 192.168.33.53, range 1-1024, allocated 0
UDP PAT pool outside:obj_192.168.33.50-55, address 192.168.33.53, range 1024-65535, allocated 6
UDP PAT pool outside, address 192.168.23.3, range 1-511, allocated 0
UDP PAT pool outside, address 192.168.23.3, range 512-1023, allocated 0
UDP PAT pool outside, address 192.168.23.3, range 1024-65535, allocated 4
UDP PAT pool outside:obj_192.168.33.50-55, address 192.168.33.54, range 1-1024, allocated 0
UDP PAT pool outside:obj_192.168.33.50-55, address 192.168.33.54, range 1024-65535, allocated 2
UDP PAT pool inside, address 192.168.13.3, range 1-511, allocated 0
UDP PAT pool inside, address 192.168.13.3, range 512-1023, allocated 0
UDP PAT pool inside, address 192.168.13.3, range 1024-65535, allocated 4
UDP PAT pool dmz1, address 192.168.34.3, range 1-511, allocated 0
UDP PAT pool dmz1, address 192.168.34.3, range 512-1023, allocated 0
UDP PAT pool dmz1, address 192.168.34.3, range 1024-65535, allocated 4
The reader is also reminded that with the flat keyword, the well-known real source ports can never be provided identical mapped source ports for reasons stated in the flat section.

1.2.1.9 Extended Keyword

The last of the important behavioral keywords is the extended keyword. The extended keyword enables extended PAT for any pool it is used with.

Theoretically (an important keyword here), the difference with extended PAT is that it enables the use of all available ports per service while regular PAT uses the range per source IP address. Service here is defined as the unique combination of source IP, destination IP and destination port. Cisco documentation describes the extended keyword as follows:

Enables extended PAT for a PAT pool. Extended PAT uses 65535 ports per service, as opposed to per IP address, by including the destination address and port in the translation information. Normally, the destination port and address are not considered when creating PAT translations, so you are limited to 65535 ports per PAT address. For example, with extended PAT, you can create a translation of 10.1.1.1:1027 when going to 192.168.1.7:23 as well as a translation of 10.1.1.1:1027 when going to 192.168.1.7:80.

To further explain the example used by Cisco, by default port 1027 for mapped IP address 10.1.1.1 will be used for only one source IP/Source port combination. In other words, if the real IP/real source port 192.168.13.1:1027 was provided the 10.1.1.1:1027 mapped IP/mapped source port, then 1027 would be taken out of the pool of ports available for PAT. If another IP 192.168.13.100:1027 needed PAT, it would have to be provided an alternate mapped source port.

In the case of extended PAT, with the above scenario, 1027 will be taken out of the pool only for the service that 192.168.13.1:1027 is using. In other words, 1027 will be pinned to the destination IP and destination port as well. This time, if another IP address 192.168.13.100:1027 needs translation, the ASA will check which service it is using. It will then check on the destination IP and destination port. As long as 192.168.13.100 is not using an identical service to 192.168.13.1, it too will be provided with port 1027.

That is the theory anyway. But as the preeminent philosopher of our times, Yogi Berra once said:

In theory there is no difference between theory and practice. In practice there is.

In practice, at least on 8.4(3), the results are a little different than what is stated in the Cisco documentation.

1.2.1.9.1 The setup and Demonstration

In an attempt to reduce the clutter, only two connections were initiated from inside to outside.

Protocol	Source IP	Source Port	Destination IP	Destination Port
UDP	192.168.13.1	10000	192.168.23.2	100
UDP	192.168.13.5	10000	192.168.23.2	200
Verification

First the output of show conn is studied to ensure that the connections’ natures are indeed what we expect them to be.

ASA1(config)# sho conn
 2 in use, 14 most used
 UDP outside 192.168.23.2:100 inside 192.168.13.1:10000, idle 0:00:06, bytes 4224, flags -
 UDP outside 192.168.23.2:200 inside 192.168.13.5:10000, idle 0:00:01, bytes 4240, flags -
Having ensured that the connections are being created properly, the next item to verify is the xlate table.

ASA1(config)# sho xlate
 2 in use, 13 most used
 Flags: D - DNS, i - dynamic, r - portmap, s - static, I - identity, T - twice
        e - extended
 UDP PAT from inside:192.168.13.5/10000 to 
outside:192.168.33.50/10000(192.168.23.2) flags rie idle 0:00:11 timeout 0:00:30
 UDP PAT from inside:192.168.13.1/10000 to 
outside:192.168.33.50/13812(192.168.23.2) flags rie idle 0:00:01 timeout 0:00:30
At this point, the St. Yogi factor comes into play rather unexpectedly. As per the Cisco documentation, the ASA should have been able to preserve the source ports for both of the connections as they are indeed using different services:

192.168.23.2:100
192.168.23.2:200
Obviously, that was not happening here. The author asks you to take his word as this scenario was repeated multiple times with various different source and destination ports. For each source/destination port combination, the results were always the same – the ASA experienced a port collision and the second PAT always received a substitute mapped source port.

The next output to be studied was the show nat pool output.

ASA1(config)# sho nat pool
UDP PAT pool outside:obj_192.168.33.50-55, address 192.168.33.50, range 1-511, allocated 0
UDP PAT pool outside:obj_192.168.33.50-55, address 192.168.33.50, range 512-1023, allocated 0
UDP PAT pool outside:obj_192.168.33.50-55, address 192.168.33.50, range 1024-65535, allocated 0
UDP PAT pool outside:obj_192.168.33.50-55, address 192.168.33.50(192.168.23.2), range 1-511, allocated 0
UDP PAT pool outside:obj_192.168.33.50-55, address 192.168.33.50(192.168.23.2), range 512-1023, allocated 0
UDP PAT pool outside:obj_192.168.33.50-55, address 192.168.33.50(192.168.23.2), range 1024-65535, allocated 2
UDP PAT pool outside, address 192.168.23.3, range 1-511, allocated 0
UDP PAT pool outside, address 192.168.23.3, range 512-1023, allocated 0
UDP PAT pool outside, address 192.168.23.3, range 1024-65535, allocated 4
UDP PAT pool inside, address 192.168.13.3, range 1-511, allocated 0
UDP PAT pool inside, address 192.168.13.3, range 512-1023, allocated 0
UDP PAT pool inside, address 192.168.13.3, range 1024-65535, allocated 4
UDP PAT pool dmz1, address 192.168.34.3, range 1-511, allocated 0
UDP PAT pool dmz1, address 192.168.34.3, range 512-1023, allocated 0
UDP PAT pool dmz1, address 192.168.34.3, range 1024-65535, allocated 4
It is abundantly clear that the ASA behavior has changed but it seems that when it comes to the “service”, the ASA is only considering the destination IP address, not the destination IP/destination port combination.

To validate this theory, one of the above connections is altered to use a different destination IP address. The new connections are as follows:

Protocol	Source IP	Source Port	Destination IP	Destination Port
UDP	192.168.13.1	10000	192.168.23.2	100
UDP	192.168.13.5	10000	192.168.23.20	200
Thus the second connection is now initiated to 192.168.23.20, a separate IP address on the outside.

Verification is repeated with the same steps as before.

The show conn output:

ASA1(config)# sho conn
2 in use, 14 most used
UDP outside 192.168.23.20:200 inside 192.168.13.5:10000, idle 0:00:01, bytes 16, flags -
UDP outside 192.168.23.2:100 inside 192.168.13.1:10000, idle 0:00:06, bytes 16, flags –
The connections are forming as desired. Next comes the show xlate output:

ASA1(config)# sho xlate
2 in use, 13 most used
Flags: D - DNS, i - dynamic, r - portmap, s - static, I - identity, T - twice
       e - extended
UDP PAT from inside:192.168.13.5/10000 to 
outside:192.168.33.50/10000(192.168.23.20) flags rie idle 0:00:06 timeout 0:00:30
UDP PAT from inside:192.168.13.1/10000 to 
outside:192.168.33.50/10000(192.168.23.2) flags rie idle 0:00:11 timeout 0:00:30
Voila, this time the ASA did not detect a port collision and the source ports were preserved for both the translations.

Finally, a look at the show nat pool to bring this issue to a close (or semi-closure):

ASA1(config)# sho nat pool
UDP PAT pool outside:obj_192.168.33.50-55, address 192.168.33.50, range 1-511, allocated 0
UDP PAT pool outside:obj_192.168.33.50-55, address 192.168.33.50, range 512-1023, allocated 0
UDP PAT pool outside:obj_192.168.33.50-55, address 192.168.33.50, range 1024-65535, allocated 0
UDP PAT pool outside:obj_192.168.33.50-55, address 192.168.33.50(192.168.23.2), range 1-511, allocated 0
UDP PAT pool outside:obj_192.168.33.50-55, address 192.168.33.50(192.168.23.2), range 512-1023, allocated 0
UDP PAT pool outside:obj_192.168.33.50-55, address 192.168.33.50(192.168.23.2), range 1024-65535, allocated 1
UDP PAT pool outside, address 192.168.23.3, range 1-511, allocated 0
UDP PAT pool outside, address 192.168.23.3, range 512-1023, allocated 0
UDP PAT pool outside, address 192.168.23.3, range 1024-65535, allocated 4
UDP PAT pool outside:obj_192.168.33.50-55, address 192.168.33.50(192.168.23.20), range 1-511, allocated 0
UDP PAT pool outside:obj_192.168.33.50-55, address 192.168.33.50(192.168.23.20), range 512-1023, allocated 0
UDP PAT pool outside:obj_192.168.33.50-55, address 192.168.33.50(192.168.23.20), range 1024-65535, allocated 1
UDP PAT pool inside, address 192.168.13.3, range 1-511, allocated 0
UDP PAT pool inside, address 192.168.13.3, range 512-1023, allocated 0
UDP PAT pool inside, address 192.168.13.3, range 1024-65535, allocated 4
UDP PAT pool dmz1, address 192.168.34.3, range 1-511, allocated 0
UDP PAT pool dmz1, address 192.168.34.3, range 512-1023, allocated 0
UDP PAT pool dmz1, address 192.168.34.3, range 1024-65535, allocated 4
This time there are two different pools that the mapped source ports can be picked from. As a result, no port-collision takes place and each translation is able to preserve its source port.

These scenarios were tested on 8.4(3), the very first version to even support the extended keyword. We were not able to secure a more current version in time to check if this was just a bug in the initial version. The Cisco documentation, however, was indeed quoted from the documentation for 8.4.
Another caveat worth mentioning is the memory impact of these various knobs, notably round-robin and extended:

Round robin, especially when combined with extended PAT, can consume a large amount of memory. Because NAT pools are created for every mapped protocol/IP address/port range, round robin results in a large number of concurrent NAT pools, which use memory. Extended PAT results in an even larger number of concurrent NAT pools.

Therefore, these options, especially in combination should be used only after careful consideration.

1.2.2 Using Manual NAT

The concepts discussed under NON are applicable, as usual, directly under Manual NAT. The blog post will show one cursory example, with the use of the round-robin flat include-reserve keyword combination. To use Manual NAT, the reader is encouraged to read the first post from this series in conjunction with the NON section of this particular post to achieve any desired results.

Configuration

ASA1(config)# nat (inside,outside) source dynamic obj_192.168.13.0_dmz1 pat-pool obj_192.168.33.50-55 ?

configure mode commands/options:
  description  Specify NAT rule description
  destination  Destination NAT parameters
  dns          Use the created xlate to rewrite DNS record
  extended     Extend PAT uniqueness to per destination instead of per interface
  flat         Translate TCP and UDP ports into flat range 1024-65535
  inactive     Disable a NAT rule
  interface    Specify interface overload
  round-robin  Specify to use PAT ip addresses in round robin instead one by one
  service      NAT service parameters

ASA1(config)# nat (inside,outside) source dynamic obj_192.168.13.0_dmz1 pat-pool obj_192.168.33.50-55 flat include-reserve
The same verification tools are used as before. The show nat pool output for this example is utterly confusing because the scenario, against best practice, is using the same source PAT pools in different places in the configuration. The output has been included for completeness but is rendered irrelevant because of the “misconfiguration”.

Verification

ASA1(config)# sho xlate
12 in use, 12 most used
Flags: D - DNS, i - dynamic, r - portmap, s - static, I - identity, T - twice
       e - extended
UDP PAT from inside:192.168.13.101/600 to outside:192.168.33.54/600 flags ri idle 0:00:04 timeout 0:00:30
UDP PAT from inside:192.168.13.101/100 to outside:192.168.33.54/100 flags ri idle 0:00:05 timeout 0:00:30
UDP PAT from inside:192.168.13.5/20000 to outside:192.168.33.53/20000 flags ri idle 0:00:02 timeout 0:00:30
UDP PAT from inside:192.168.13.5/10000 to outside:192.168.33.53/10000 flags ri idle 0:00:04 timeout 0:00:30
UDP PAT from inside:192.168.13.5/700 to outside:192.168.33.53/700 flags ri idle 0:00:04 timeout 0:00:30
UDP PAT from inside:192.168.13.5/600 to outside:192.168.33.53/600 flags ri idle 0:00:05 timeout 0:00:30
UDP PAT from inside:192.168.13.5/200 to outside:192.168.33.53/200 flags ri idle 0:00:05 timeout 0:00:30
UDP PAT from inside:192.168.13.5/100 to outside:192.168.33.53/100 flags ri idle 0:00:05 timeout 0:00:30
UDP PAT from inside:192.168.13.1/20000 to outside:192.168.33.55/20000 flags ri idle 0:00:04 timeout 0:00:30
UDP PAT from inside:192.168.13.1/10000 to outside:192.168.33.55/10000 flags ri idle 0:00:04 timeout 0:00:30
UDP PAT from inside:192.168.13.1/700 to outside:192.168.33.55/700 flags ri idle 0:00:04 timeout 0:00:30
UDP PAT from inside:192.168.13.1/200 to outside:192.168.33.55/200 flags ri idle 0:00:04 timeout 0:00:30

ASA1(config)# sho nat pool
UDP PAT pool outside:obj_192.168.33.50-55, address 192.168.33.55, range 1-511, allocated 1
UDP PAT pool outside:obj_192.168.33.50-55, address 192.168.33.55, range 512-1023, allocated 1
UDP PAT pool outside:obj_192.168.33.50-55, address 192.168.33.55, range 1024-65535, allocated 2
UDP PAT pool outside:obj_192.168.33.50-55, address 192.168.33.53, range 1-511, allocated 2
UDP PAT pool outside:obj_192.168.33.50-55, address 192.168.33.53, range 512-1023, allocated 2
UDP PAT pool outside:obj_192.168.33.50-55, address 192.168.33.53, range 1024-65535, allocated 2
UDP PAT pool outside, address 192.168.23.3, range 1-511, allocated 0
UDP PAT pool outside, address 192.168.23.3, range 512-1023, allocated 0
UDP PAT pool outside, address 192.168.23.3, range 1024-65535, allocated 4
UDP PAT pool outside:obj_192.168.33.50-55, address 192.168.33.54, range 1-511, allocated 1
UDP PAT pool outside:obj_192.168.33.50-55, address 192.168.33.54, range 512-1023, allocated 1
UDP PAT pool outside:obj_192.168.33.50-55, address 192.168.33.54, range 1024-65535, allocated 0
UDP PAT pool inside, address 192.168.13.3, range 1-511, allocated 0
UDP PAT pool inside, address 192.168.13.3, range 512-1023, allocated 0
UDP PAT pool inside, address 192.168.13.3, range 1024-65535, allocated 4
UDP PAT pool dmz1, address 192.168.34.3, range 1-511, allocated 0
UDP PAT pool dmz1, address 192.168.34.3, range 512-1023, allocated 0
UDP PAT pool dmz1, address 192.168.34.3, range 1024-65535, allocated 4

ASA1(config)# sho nat detail
Manual NAT Policies (Section 1)
1 (inside) to (any) source dynamic obj_192.168.13.0-13.50 obj_192.168.33.33   inactive
    translate_hits = 0, untranslate_hits = 0
    Source - Origin: 192.168.13.1-192.168.13.50, Translated: 192.168.33.33/32
2 (inside) to (outside) source dynamic obj_192.168.13.0_dmz1 pat-pool obj_192.168.33.50-55flat include-reserve
    translate_hits = 12, untranslate_hits = 0
    Source - Origin: 192.168.13.0/24, Translated (PAT): 192.168.33.50-192.168.33.55

Auto NAT Policies (Section 2)
1 (inside) to (dmz1) source dynamic obj_192.168.13.0_dmz1 pat-pool obj_192.168.33.60-65 round-robin
    translate_hits = 0, untranslate_hits = 0
    Source - Origin: 192.168.13.0/24, Translated (PAT): 192.168.33.60-192.168.33.65
2 (inside) to (outside) source dynamic obj_192.168.13.0_outside pat-pool obj_192.168.33.50-55 round-robin
    translate_hits = 12, untranslate_hits = 0
    Source - Origin: 192.168.13.0/24, Translated (PAT): 192.168.33.50-192.168.33.55