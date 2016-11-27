import argparse
import socket
import select
import time
import sys
from collections import deque
import random
#global constants

#constants for SYN,ACK,FIN bit math
SYN = 4
ACK = 2
FIN = 1
BIT16 = 65536
BIGNUMBER = 30000
#takes in the binary flags (SYN,ACK,FIN), segment Number and Acknowledgement number before returning a 5 byte string that can be put in front of the data
   #the protocol atm is 5 bytes:
    # Byte 1: 5xRES (reserved padding bits), SYN, ACK, FIN  e.g. 00000110 is SYN+ACK
    # Byte 2-3: 16-bit Segment number (first byte sent)
    # Byte 4-5: 16-bit ACK number (next byte expected)
    # No randomisation of starting segment/ack numbers yet, but that won't be handled by these functions

class dataSeg:

    def __init__(self, num, data):
        self.num = num
        self.data = data
        self.size = len(data)
        self.timeSent = 0
        self.retrans = False #keeps track of whether or not this is a retransmitted segment or not

#Takes in the 3 flags SYN,ACK,FIN and also takes in the Segment and Ack numbers. Outputs a 5 byte header to be attached to the appropriate packet
def packHeader(SYNset,ACKset,FINset,segNum,ackNum):
    retVal = 0
    if SYNset:
        retVal = retVal + SYN
    if ACKset:
        retVal = retVal + ACK
    if FINset:
        retVal = retVal + FIN

    retVal = str(unichr(retVal))
    for hexNum in [hex(segNum)[2:],hex(ackNum)[2:]]:
        while len(str(hexNum)) != 4:
            hexNum = '0' + str(hexNum)
        retVal += hexNum.decode('hex')


    return retVal

#Takes in the header (5 bytes) and unpacks it, returning a flag(string, like 'SYNACK'), the segment number and the acknowledgement number
def unpackHeader(header):
    # print "unpacking"

    flagNum = ord(header[0])
    flag = ""
    if flagNum >= SYN:
        flag += "SYN"
        flagNum = flagNum - SYN
    if flagNum >= ACK:
        flag += "ACK"
        flagNum = flagNum - ACK
    if flagNum >= FIN:
        flag += "FIN"

    segHex,ackHex = header[1:3],header[3:5]
    segNum,ackNum = int(segHex.encode('hex'),16),int(ackHex.encode('hex'),16)
    # print flag, segNum, ackNum
    return [flag, segNum, ackNum]

def main():
    #doing parsing of args
    parser = argparse.ArgumentParser()
    parser.add_argument("host", help= "the IP address of the host machine on which the Receiver is running, like 127.0.0.1")
    parser.add_argument("port", help=" the port number on which Receiver is expecting to receive packets from the sender., like 3456")
    parser.add_argument("inName", help="the name of the text file that has to be transferred from sender to receiver using this program. ")
    parser.add_argument("mws", help="the maximum window size used by this program (in bytes). If this number is over 20000 then 20000 will be the mws used by the sender")
    parser.add_argument("mss", help= "the maximum segment size which is the maximum amount of data (in bytes) carried in each STP segment. If this is larger than the mws or 30000 then the sender will use whichever of the previous 2 that is smaller")
    parser.add_argument("timeout", help= "the value of timeout in milliseconds")
    parser.add_argument("pdrop", help= "the probability that a STP data segment which is ready to be transmitted will be dropped, like 0.5")
    parser.add_argument("seed", help= "The seed for my random number generator. Just pick a whole number lol")
    args = parser.parse_args()


    #dealing with file formatting and splitting into packet-sized chunks (also making the arguments not strings)
    f = open( args.inName,'rb')
    mss = int(args.mss)
    mws = int(args.mws)
    if mws > 20000:
        mws = 20000
    if mss > mws:
        mss = mws
    timeout = float(args.timeout)/1000
    pdrop = float(args.pdrop)
    random.seed(int(args.seed))

    #sorting out socket constants
    IP = args.host
    PORT = int(args.port)
    socket.setdefaulttimeout(1)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM,0)#make udp socket and use it to connect
    s.connect((IP,PORT))


    logList = [] #will hold a list of strings that will eventually become the log file for PingClient


    #making the packets
    fileTxt = f.read()
    fileSize = len(fileTxt)
    numPackets = -(-fileSize//mss) #// is integer division rounding down, double negative rounds up instead
    packet = []
    for i in range(numPackets):
        if i < numPackets - 1:
            packet.append(dataSeg(i,fileTxt[(i*mss):((i+1)*mss)]))
        else:
            packet.append(dataSeg(i,fileTxt[(i*mss):]))

    #we initiate the handshake
    client_isn = random.randint(0,pow(2,16)-5) #right now we don't bother with randomising the isn since it's not required, but im leaving the infrastructure here in case
    initHand = packHeader(True,False,False,client_isn,0) #SYN packet
    s.send(initHand)    
    initTime = time.time() #holds time when we started ---for logging purposes
    logList.append(["snd",initTime,"S",client_isn,0,0]) #all appendices to logList are just lines added to the log

    data, addr = s.recvfrom(2048) #should recieve SYNACK
    flag, segNum, ackNum = unpackHeader(data[:5])
    if flag != "SYNACK": #if it's an attempt to start file transfer, we boot up the handshake...otherwise something has gone wrong
        print "recieved wrong header SYNACK???"
        sys.exit()
    logList.append(["rcv",time.time(),"SA",segNum,0,ackNum])

    #we reply to handshake to finish it off and wait for ack of SYNACK
    initHand = packHeader(False,True,False,client_isn + 1, segNum) #send ACK
    s.send(initHand)
    logList.append(["snd",time.time(),"A",client_isn+1,0,segNum])

    data, addr = s.recvfrom(2048) #should recieve ACK
    flag, segNum, ackNum = unpackHeader(data[:5])
    if flag != "ACK": #if it's an attempt to start file transfer, we boot up the handshake
        print "recieved wrong header ACK???"
        sys.exit()
    logList.append(["rcv",time.time(),"A",segNum,0,ackNum])
        #Main loop where data is sent
#------------------------------------------------------------------------------------------------------------------------------------
#------------------------------------------------------------------------------------------------------------------------------------
#------------------------------------------------------------------------------------------------------------------------------------
    #setting variables we'll need before the loop starts
    client_isn += 1
    i = 0
    LastByteSent = client_isn
    LastByteAckd = ackNum
    queSend = deque(packet) #making our send queue
    queSend.reverse() #but it's the wrong way round so we flip it
    queAck = deque()
    fastRetrans = 0
    cDrop, cRetrans, cDups = [0,0,0] #these are for logging purposes
    fin = False

    print "Sending file now..."
    while flag != "ACKFIN":

        readable, writable, err = select.select([s],[s],[s]) #using select to poll our socket to see if it is readable

        for sock in writable:#if s is writable (it should be), there are packets in the send queue AND one of the next two conditions is met:
            if len(queSend): #1. sending the next packet in the queue will not break the window, or 2. the next packet is a retransmission and is already in the window
                if (LastByteSent - LastByteAckd - queSend[-1].size <= mws) or ( queSend[-1].retrans ): #old definition (ignore this) --> client_isn + (queSend[-1].num*mss) + (queSend[-1].size)) < LastByteSent
                    curPack = queSend.pop()
                    packHead = packHeader(False,False,False, (client_isn + (curPack.num*mss))%BIT16, segNum%BIT16) #segNum is the segment Number from the server
                    curPack.timeSent = time.time()
                    # print "sending ", curPack.num*mss + client_isn
                    if random.random() > pdrop: #if the random number is more than pdrop then it can be sent. Otherwise, it gets dropped (this is the PLD module lol)
                        sock.send(packHead + curPack.data)
                        logList.append(["snd",time.time(),"D",(client_isn + (curPack.num*mss)),len(curPack.data),segNum])
                        if curPack.retrans:
                            cRetrans += 1
                    else:
                        # print "~~~~~~~~~~~~~~~~~DROPPED~~~~~~~~~~~~~~~~"
                        logList.append(["drop",time.time(),"D",client_isn + (curPack.num*mss),len(curPack.data),segNum])
                        cDrop += 1


                    if LastByteSent < (client_isn + (curPack.num*mss) + (curPack.size)): #update LastByteSent appropriately
                        LastByteSent = client_isn + (curPack.num*mss) + (curPack.size)

                    queAck.appendleft(curPack) #add the sent (or dropped) packet to the ack queue where it waits to be acked
            else: #if both queues are empty we have finished transmitting the file. Send FIN Segment and wait for finack
                if len(queAck) + len(queSend) == 0 and fin == False:        
                    finHand = packHeader(False,False,True,LastByteAckd%BIT16,segNum%BIT16) 
                    s.send(finHand)
                    logList.append(["snd",time.time(),"F",LastByteAckd,0,segNum])
                    print "File successfully sent, teardown Request sent"
                    fin = True


        for sock in readable: #if there's something to be read....
            data, addr = sock.recvfrom(2048) # just chill and print acks for now
            flag, segNum, ackNum = unpackHeader(data[:5])
            # print LastByteAckd, ackNum, BIGNUMBER
            while ackNum + BIGNUMBER< LastByteAckd:
                ackNum += BIT16

            logList.append(["rcv",time.time(),"A",segNum,0,ackNum])
            if ackNum == LastByteAckd: #we check here for duplicate acks
                fastRetrans += 1
                cDups += 1
            else:
                fastRetrans = 0
                # print LastByteAckd, " becomes ", ackNum
                LastByteAckd = ackNum

            # print "recieved Ack: ", ackNum
            if fastRetrans == 0: #if we have gotten a different ack, we make sure to remove all packets waiting to be acknowledged that have a sequence number less than the ack
                k=0
                while k < len(queAck):
                    if (queAck[k].num*mss + queAck[k].size + client_isn <= ackNum):
                        # print "removing: ", str(queAck[k].num*mss + queAck[k].size + client_isn)
                        queAck.remove(queAck[k])
                    else:
                        k+=1   

                while k < len(queSend):#we do the same from the send queue which cuts down on wasteful retransmissions
                    if(ackNum > (client_isn + (queSend[k].num*mss))):
                        # print "already ackd: ", str(queSend[k].num*mss + queSend[k].size + client_isn)      
                        queSend.remove(queSend[k])
                    else:
                        k+=1

            elif fastRetrans == 3: #fast retransmit -- will only happen once per packet unless the retransmit also times out, whereupon fastRetrnas gets set back to 0 again
                # print "||||||||||||||||FAST||||||||"
                # print client_isn, ackNum, LastByteAckd
                queSend.append(packet[(ackNum - client_isn)//mss]) #put the triplicate ackd packet at the front of the send queue
                queSend[-1].retrans = True

        k=0
        # temp = ""
        #loop over queAck for debug and also to spot timeouts
        while k < len(queAck):
            if queAck[k].timeSent + timeout < time.time():#check for timeouts
                if(queAck[k].num*mss + queAck[k].size + client_isn == LastByteAckd and fastRetrans > 3): #if a fast retransmitted packet has timed out then we allow it to be fast retransmitted again in the event the timeout packet drops
                    fastRetrans = 0
                # print "Timed out packet", str(queAck[k].num*mss + client_isn), "time sent: ", queAck[k].timeSent, "vs. ", time.time()
                queSend.append(packet[queAck[k].num])#since this packet timed out we throw it at the front of the queue to be resent immediately
                queSend[-1].retrans = True
                queAck.remove(queAck[k])
            else:
                # temp = temp + str(queAck[k].num*mss + queAck[k].size + client_isn) + ", "
                k += 1



        # print temp
#------------------------------------------------------------------------------------------------------------------------------------
#------------------------------------------------------------------------------------------------------------------------------------
#------------------------------------------------------------------------------------------------------------------------------------


    # while flag != "ACKFIN": #this is a loop to pick up all leftover acks sent by the server (the client often realises it has finished while some of it's now useless packets are still in transit)
    #     data, addr = s.recvfrom(2048) 
    #     flag, segNum, ackNum = unpackHeader(data[:5])
    #     while ackNum < LastByteAckd:
    #         ackNum += BIT16
    #     if flag != "ACKFIN": 

    #         # print "recieved wrong header ACKFIN???"
    #         logList.append(["rcv",time.time(),"A",segNum,0,ackNum])

    #         if ackNum == LastByteAckd: #we check here for duplicate acks
    #             cDups += 1
    #         else:
    #             LastByteAckd = ackNum

    logList.append(["rcv",time.time(),"FA",segNum,0,ackNum])
    print "ACKFIN recieved, sending final ACK and closing down"
    finHand = packHeader(False,True,False,(LastByteAckd+1)%BIT16,segNum%BIT16) 
    s.send(finHand)
    logList.append(["snd",time.time(),"A",LastByteAckd+1,0,segNum])
    s.shutdown(socket.SHUT_RDWR)
    s.close()
    print("DONE! Writing log...")
    f = open("Sender_log.txt", 'w')
    f.write("Action \ttime \ttype \tseq \tsize\tack\n")
    for line in logList:
        line[1] = str(round(line[1] - initTime,3))
        for obj in line:
            f.write(str(obj)+"\t")
            
        f.write("\n")

    f.write("Amount of (original) Data Transferred (in bytes): " + str(fileSize) + "\n")
    f.write("Number of Data Segments Sent (excluding retransmissions): " + str(numPackets) + "\n")
    f.write("Number of (all) Packets Dropped (by the PLD module): " + str(cDrop) + "\n")
    f.write("Number of Retransmitted Segments: " + str(cRetrans) + "\n")
    f.write("Number of Duplicate Acknowledgements received: " + str(cDups) + "\n")
    f.close()
    print("FINISHED LOG")
if __name__ == "__main__": #since packHeader and unpackHeader are exported to PingServer we only want main() to run when it actually runs
    main()